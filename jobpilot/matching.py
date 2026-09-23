"""Deterministic JD-to-profile matching with a documented rubric.

The score is a transparent weighted rubric. It exists to *rank postings for
human review*; it does **not** predict hiring outcomes and must not be read as
one. Every component is computed from the master profile and the JD text only -
there is no model and no opaque "match score out of 100".

Keyword coverage is exact: terms the profile supports are listed as matched;
terms the JD asks for that the profile does not support are listed as
**gaps** and are never inserted into a generated resume.
"""

from __future__ import annotations

import re
from functools import lru_cache

from jobpilot.config import Config
from jobpilot.facts import content_tokens
from jobpilot.filtering import assess_location
from jobpilot.lexicon import extract_terms, normalize, profile_terms
from jobpilot.models import KeywordCoverage, JobPosting, MatchResult
from jobpilot.profile import Profile
from jobpilot.window import WindowInfo, classify_window

RUBRIC_VERSION = "1.1"

# Role-relevance weights. A target-domain term in the *title* is strong evidence
# that the role is what it says it is. A mention in the body is discounted
# heavily and capped below the strong-band floor, so company boilerplate ("our
# machine-learning platform...") cannot, on its own, make an unrelated role look
# relevant. A title match alone reaches the floor; a title match plus supporting
# body terms climbs toward the top of the range.
TITLE_HIT_WEIGHT = 0.5
BODY_HIT_WEIGHT = 0.1
BODY_HIT_MAX = 0.4

# Section headings that start the *role* part of an ATS description; everything
# before the first one is treated as company boilerplate. Company blurbs
# routinely mention "machine learning", "generative AI" and other target terms,
# and on a sparse posting that boilerplate is the entire description - so
# counting it as role content lets an unrelated internship look relevant. When
# no such heading is present the whole description is used, as before.
ROLE_HEADINGS = (
    "what you'll do",
    "what you will do",
    "what you'll be doing",
    "what you will be doing",
    "responsibilities",
    "your responsibilities",
    "key responsibilities",
    "the role",
    "your role",
    "about the role",
    "about this role",
    "role overview",
    "position overview",
    "job overview",
    "job description",
    "role description",
    "the opportunity",
    "requirements",
    "qualifications",
    "your qualifications",
    "what we're looking for",
    "what we are looking for",
    "who you are",
    "who we're looking for",
    "your background",
    "skills and experience",
    "what you'll need",
    "what you will need",
    "about the internship",
    "internship overview",
    "the internship",
)


def _role_description(description: str) -> str:
    """Return the role-specific part of a description, dropping company blurbs.

    A heading line short-circuits everything above it (the company/team blurb).
    Headings are matched as short standalone lines so an inline use of the word
    'responsibilities' in prose does not truncate a role description.
    """
    lines = (description or "").splitlines()
    for index, line in enumerate(lines):
        header = normalize(line).strip(" :*#-\u2013\u2014\t")
        if not header or len(header) > 48:
            continue
        if any(header == h or header.startswith(h + " ") for h in ROLE_HEADINGS):
            return "\n".join(lines[index:])
    return description or ""


def _role_text(posting: JobPosting) -> str:
    role = _role_description(posting.description)
    return " ".join(p for p in [posting.title, role] if p)


@lru_cache(maxsize=4096)
def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", re.IGNORECASE)


def _phrase_present(norm_text: str, phrase: str) -> bool:
    return _phrase_re(phrase).search(norm_text) is not None


class Matcher:
    def __init__(self, profile: Profile, config: Config):
        self.profile = profile
        self.config = config
        self._profile_terms = set(profile_terms(profile))
        self._profile_vocab = set(content_tokens(profile.raw_text))

    def match(self, posting: JobPosting, window_info: WindowInfo | None = None) -> MatchResult:
        cfg = self.config.match
        jd_text = posting.searchable_text()
        # Skills and target relevance come from the *role* text (title + the
        # role section), not company boilerplate, so a blurb cannot inflate
        # coverage or relevance.
        role_text = _role_text(posting)
        terms = extract_terms(role_text)
        matched = [t for t in terms if t in self._profile_terms]
        missing = [t for t in terms if t not in self._profile_terms]
        coverage = KeywordCoverage(matched=matched, missing=missing)

        if terms:
            skill_coverage = coverage.ratio
        else:
            skill_coverage = 0.5  # neutral when the JD exposes no extractable skills

        role_relevance, domain_scores = self._role_relevance(posting)

        loc = assess_location(posting, cfg=self.config.filter)
        location_fit = loc.score

        win = window_info or classify_window(jd_text, self.config.filter, prose=posting.description)
        if win.overlaps is True:
            window_fit = win.confidence
        elif win.overlaps is False:
            window_fit = 0.0
        else:
            window_fit = 0.3

        from jobpilot.filtering import is_internship

        seniority_fit = 1.0 if is_internship(posting, self.config.filter) else 0.0

        components = {
            "skill_coverage": skill_coverage,
            "role_relevance": role_relevance,
            "location_fit": location_fit,
            "window_fit": window_fit,
            "seniority_fit": seniority_fit,
        }
        weights = {k: float(v) for k, v in cfg.weights.items()}
        total_weight = sum(weights.get(k, 0.0) for k in components) or 1.0
        contributions = {k: weights.get(k, 0.0) * components[k] for k in components}
        score = sum(contributions.values()) / total_weight

        band, band_note = self._band(score, role_relevance, cfg)

        reasons = self._reasons(
            posting, coverage, components, domain_scores, loc.detail, win, band_note
        )
        rubric = {
            "version": RUBRIC_VERSION,
            "description": (
                "Weighted rubric over deterministic components. Ranks postings for "
                "human review; it does not predict hiring outcomes."
            ),
            "weights": weights,
            "components": {
                k: {
                    "score": round(components[k], 4),
                    "weight": weights.get(k, 0.0),
                    "contribution": round(contributions[k], 4),
                }
                for k in components
            },
            "formula": "score = sum(weight_i * component_i) / sum(weight_i)",
            "coverage": coverage.to_dict(),
            "bands": {"strong": cfg.strong_threshold, "shortlist": cfg.shortlist_threshold},
            "strong_requirements": {
                "min_role_relevance": float(cfg.strong_min_role_relevance),
                "target_domains": list(cfg.target_terms),
            },
        }

        return MatchResult(
            score=score,
            reasons=reasons,
            rubric=rubric,
            coverage=coverage,
            missing_keywords=missing,
            band=band,
        )

    @staticmethod
    def _band(score: float, role_relevance: float, cfg) -> tuple[str, str | None]:
        """Assign a band, capping `strong` when role relevance is too low.

        The score threshold alone cannot tell a genuinely relevant role from an
        unrelated internship that happens to be in India with an ideal window:
        location, seniority and a single soft-skill keyword can carry an
        unrelated posting over it. `strong` is the auto-apply band, so it
        additionally requires the posting's role relevance to reach the
        configured floor; below it the posting is capped to `shortlist`
        (tailored and queued for review) and the reason string says why.
        """
        if score >= cfg.strong_threshold:
            floor = float(cfg.strong_min_role_relevance)
            if role_relevance < floor:
                domains = ", ".join(cfg.target_terms) or "none configured"
                note = (
                    f"strong band withheld: role relevance {role_relevance:.2f} is below the "
                    f"{floor:.2f} minimum for the configured target domains ({domains})"
                )
                return "shortlist", note
            return "strong", None
        if score >= cfg.shortlist_threshold:
            return "shortlist", None
        return "reject", None

    def _role_relevance(self, posting: JobPosting) -> tuple[float, dict[str, float]]:
        title_norm = normalize(posting.title)
        body_norm = normalize(_role_description(posting.description))
        scores: dict[str, float] = {}
        for domain, phrases in self.config.match.target_terms.items():
            title_hit = any(_phrase_present(title_norm, normalize(p)) for p in phrases)
            body_hits = sum(1 for p in phrases if _phrase_present(body_norm, normalize(p)))
            score = (TITLE_HIT_WEIGHT if title_hit else 0.0) + min(
                BODY_HIT_MAX, body_hits * BODY_HIT_WEIGHT
            )
            scores[domain] = round(min(1.0, score), 4)
        best = max(scores.values()) if scores else 0.0
        return best, scores

    @staticmethod
    def _reasons(
        posting: JobPosting,
        coverage: KeywordCoverage,
        components: dict[str, float],
        domain_scores: dict[str, float],
        location_detail: str,
        win: WindowInfo,
        band_note: str | None = None,
    ) -> list[str]:
        total = len(coverage.matched) + len(coverage.missing)
        reasons = [
            f"skill coverage {coverage.ratio:.0%} ({len(coverage.matched)}/{total} JD terms supported by profile)",
            f"role relevance {components['role_relevance']:.2f} "
            f"({', '.join(f'{k}={v:.2f}' for k, v in domain_scores.items()) or 'no target domains'})",
            f"location fit {components['location_fit']:.2f}: {location_detail}",
            f"window fit {components['window_fit']:.2f}: {win.detail}",
            f"seniority fit {components['seniority_fit']:.2f}: "
            f"{'internship' if components['seniority_fit'] else 'not an internship'}",
        ]
        if band_note:
            reasons.append(band_note)
        if coverage.missing:
            shown = ", ".join(coverage.missing[:12])
            more = "" if len(coverage.missing) <= 12 else f" (+{len(coverage.missing) - 12} more)"
            reasons.append(f"gaps (never inserted): {shown}{more}")
        if coverage.matched:
            reasons.append(f"supported JD terms: {', '.join(coverage.matched[:12])}")
        return reasons
