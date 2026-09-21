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

RUBRIC_VERSION = "1.0"


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
        terms = extract_terms(jd_text)
        matched = [t for t in terms if t in self._profile_terms]
        missing = [t for t in terms if t not in self._profile_terms]
        coverage = KeywordCoverage(matched=matched, missing=missing)

        if terms:
            skill_coverage = coverage.ratio
        else:
            skill_coverage = 0.5  # neutral when the JD exposes no extractable skills

        role_relevance, domain_scores = self._role_relevance(posting, jd_text)

        loc = assess_location(posting, cfg=self.config.filter)
        location_fit = loc.score

        win = window_info or classify_window(jd_text, self.config.filter)
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

        if score >= cfg.strong_threshold:
            band = "strong"
        elif score >= cfg.shortlist_threshold:
            band = "shortlist"
        else:
            band = "reject"

        reasons = self._reasons(
            posting, coverage, components, domain_scores, loc.detail, win
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
        }

        return MatchResult(
            score=score,
            reasons=reasons,
            rubric=rubric,
            coverage=coverage,
            missing_keywords=missing,
            band=band,
        )

    def _role_relevance(self, posting: JobPosting, jd_text: str) -> tuple[float, dict[str, float]]:
        norm = normalize(jd_text)
        title_norm = normalize(posting.title)
        scores: dict[str, float] = {}
        for domain, phrases in self.config.match.target_terms.items():
            hits = sum(1 for p in phrases if _phrase_present(norm, normalize(p)))
            scores[domain] = min(1.0, hits / 3.0)
        best = max(scores.values()) if scores else 0.0
        # Title match is a strong signal that the role is in the target space.
        for phrases in self.config.match.target_terms.values():
            if any(_phrase_present(title_norm, normalize(p)) for p in phrases):
                best = min(1.0, best + 0.2)
                break
        return best, scores

    @staticmethod
    def _reasons(
        posting: JobPosting,
        coverage: KeywordCoverage,
        components: dict[str, float],
        domain_scores: dict[str, float],
        location_detail: str,
        win: WindowInfo,
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
        if coverage.missing:
            shown = ", ".join(coverage.missing[:12])
            more = "" if len(coverage.missing) <= 12 else f" (+{len(coverage.missing) - 12} more)"
            reasons.append(f"gaps (never inserted): {shown}{more}")
        if coverage.matched:
            reasons.append(f"supported JD terms: {', '.join(coverage.matched[:12])}")
        return reasons
