"""Hard filters: internship, window, and India / remote-from-India eligibility.

These run *before* scoring. A posting that fails any hard filter is recorded with
its rejection reasons but never scored for tailoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobpilot.models import CheckResult, FilterResult, JobPosting
from jobpilot.window import WindowInfo, classify_window

# Countries/regions that, if the only location named, mean onsite work there.
# Country tokens are matched as whole words, so a bare "us" catches "Remote, US",
# "Remote (US)" and "US - Remote" as well as "usa" / "u.s.".
ABROAD_TERMS = [
    "united states", "usa", "u.s.", "u.s", "us",
    "united kingdom", "uk", "canada", "germany", "france", "netherlands",
    "singapore", "australia", "japan", "china", "brazil", "mexico", "poland",
    "spain", "italy", "ireland", "switzerland", "sweden", "uae", "dubai",
    "emea", "apac", "latam", "europe",
]
GLOBAL_TERMS = ["worldwide", "anywhere", "global", "any location", "fully remote"]

# Signals that a posting restricts where (or for whom) the role is open, used
# when the structured location field names no country. The bare token "us" is
# excluded from the country list because it appears constantly in English prose
# ("join us", "about us"); the explicit phrases below catch the real
# restrictions without that false positive.
WORK_AUTH_PROSE_TERMS = [
    *(t for t in ABROAD_TERMS if t not in {"us", "u.s.", "u.s"}),
    "in the us", "in the u.s.", "in the usa",
    "within the us", "within the u.s.",
    "us only", "u.s. only", "usa only",
    "us-based", "us based",
    "remote (us)", "remote (usa)", "remote - us", "remote, us",
    "must be located in", "must reside in", "must be based in",
    "authorized to work in", "authorised to work in",
    "eligible to work in", "legally authorized to work", "legally authorised to work",
    "work authorization required", "work authorisation required",
    "us work authorization", "requires us citizenship",
]


def _find(text: str, terms: list[str]) -> str | None:
    """Return the first term present in text as a whole phrase (word-bounded)."""
    low = (text or "").lower()
    for term in terms:
        if not term:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(term.lower().strip())}(?![a-z0-9])", low):
            return term
    return None


def _named_place_tokens(location: str, cfg) -> list[str]:
    """Location tokens left after removing remote/global qualifiers."""
    text = (location or "").lower()
    for term in [*GLOBAL_TERMS, *cfg.remote_keywords]:
        term = (term or "").lower().strip()
        if term:
            text = re.sub(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", " ", text)
    return re.findall(r"[a-z0-9]+", text)


def is_internship(posting: JobPosting, cfg) -> bool:
    haystack = f"{posting.title} {posting.employment_type} {posting.description[:1500]}"
    return _find(haystack, cfg.internship_keywords) is not None


def internship_check(posting: JobPosting, cfg) -> CheckResult:
    haystack = f"{posting.title} {posting.employment_type} {posting.description[:1500]}"
    hit = _find(haystack, cfg.internship_keywords)
    if hit:
        return CheckResult("internship", True, f"matched internship keyword {hit!r}", 1.0)
    return CheckResult("internship", False, "not identifiable as an internship", 0.0)


def seniority_check(posting: JobPosting, cfg) -> CheckResult:
    title = posting.title or ""
    hit = _find(title, cfg.seniority_reject_keywords)
    if hit and not _find(title, cfg.internship_keywords):
        return CheckResult("seniority", False, f"seniority keyword {hit!r} in title", 0.0)
    return CheckResult("seniority", True, "no seniority conflict", 1.0)


def fulltime_check(posting: JobPosting, cfg) -> CheckResult:
    structured = f"{posting.title} {posting.employment_type}"
    description = posting.description[:1500]
    hit = _find(structured, cfg.fulltime_reject_keywords)
    if hit:
        return CheckResult("fulltime", False, f"full-time signal {hit!r}", 0.0)
    desc_hit = _find(description, cfg.fulltime_reject_keywords)
    internship_hit = _find(f"{structured} {description}", cfg.internship_keywords)
    if desc_hit:
        if internship_hit:
            return CheckResult(
                "fulltime",
                True,
                f"ambiguous: full-time signal {desc_hit!r} in the description alongside "
                f"internship signal {internship_hit!r}; review before applying",
                0.3,
                review_only=True,
            )
        return CheckResult("fulltime", False, f"full-time signal {desc_hit!r} in the description", 0.0)
    if _find(structured, cfg.internship_keywords):
        return CheckResult("fulltime", True, "internship keyword present", 1.0)
    if _find(description, cfg.internship_keywords):
        return CheckResult("fulltime", True, "internship keyword in description", 0.7)
    return CheckResult("fulltime", True, "no full-time signal", 0.5)


@dataclass
class LocationAssessment:
    score: float
    eligible: bool
    detail: str
    auto_apply_ok: bool = True


def assess_location(posting: JobPosting, cfg) -> LocationAssessment:
    location = (posting.location or "").lower()
    desc = (posting.description or "").lower()
    combined = f"{location} {desc[:600]}"

    india_local = _find(location, cfg.india_keywords)
    abroad_local = _find(location, ABROAD_TERMS)
    global_local = _find(location, GLOBAL_TERMS)
    remote_local = _find(location, cfg.remote_keywords)
    location_names_country = bool(india_local or abroad_local)
    remote = posting.is_remote is True or remote_local is not None

    reject_local = _find(location, cfg.location_reject_keywords)
    if reject_local:
        return LocationAssessment(0.0, False, f"location/work-authorization restriction: {reject_local!r}")

    if location_names_country:
        reject_prose = _find(combined, cfg.location_reject_keywords)
        if reject_prose:
            return LocationAssessment(
                0.0, False, f"location/work-authorization restriction: {reject_prose!r}"
            )
    else:
        prose = _find(desc[:600], [*cfg.location_reject_keywords, *WORK_AUTH_PROSE_TERMS])
        if prose:
            return LocationAssessment(
                0.85 if remote else 0.5,
                True,
                f"location/work-authorization restriction stated in the description ({prose!r}); "
                "review before applying",
                auto_apply_ok=False,
            )

    if india_local:
        return LocationAssessment(1.0, True, "location is in India")
    if global_local:
        return LocationAssessment(0.95, True, "globally remote")

    # The structured location names a place that is neither a recognised country
    # nor an explicit remote/global form. It is not confirmably open to India, so
    # a description-level India mention or a remote tag must not promote it to
    # auto-apply; route it to the review queue instead. A remote keyword only
    # counts as an explicit remote form when no other place token remains.
    unrecognized_place = (
        bool(location.strip())
        and not location_names_country
        and not global_local
        and bool(_named_place_tokens(location, cfg))
    )
    if unrecognized_place and (
        _find(combined, cfg.india_keywords) or posting.is_remote is True or remote_local is not None
    ):
        return LocationAssessment(
            0.5,
            True,
            f"location {posting.location!r} is not confirmably open to India; review before applying",
            auto_apply_ok=False,
        )

    if not location_names_country and _find(combined, cfg.india_keywords):
        return LocationAssessment(0.9, True, "India mentioned in posting")

    if remote and not abroad_local:
        return LocationAssessment(0.85, True, "remote with no country restriction")
    if remote and abroad_local:
        if cfg.allow_onsite_abroad:
            return LocationAssessment(0.5, True, f"remote restricted to {abroad_local}, allowed by config")
        return LocationAssessment(0.1, False, f"remote restricted to non-India region {abroad_local!r}")

    if not location.strip():
        if getattr(cfg, "allow_unknown_location", False):
            return LocationAssessment(0.4, True, "location unspecified (allowed by config)")
        return LocationAssessment(0.0, False, "location unspecified")

    if abroad_local:
        if cfg.allow_onsite_abroad:
            return LocationAssessment(0.4, True, f"onsite abroad ({abroad_local}), allowed by config")
        return LocationAssessment(0.0, False, f"onsite location abroad ({abroad_local!r})")
    return LocationAssessment(0.2, False, f"location not confirmably open to India ({posting.location!r})")


def review_only_reasons(posting: JobPosting, cfg) -> list[str]:
    """Reasons ambiguous postings must be human-reviewed before auto-applying.

    A restriction or full-time cue that appears only in the description is too
    weak to auto-apply on, but too uncertain to discard: the posting stays in
    the pipeline for scoring and goes to the review queue.
    """
    reasons: list[str] = []
    loc = assess_location(posting, cfg)
    if not loc.auto_apply_ok:
        reasons.append(loc.detail)
    ft = fulltime_check(posting, cfg)
    if ft.review_only:
        reasons.append(ft.detail)
    return reasons


def location_check(posting: JobPosting, cfg) -> CheckResult:
    a = assess_location(posting, cfg)
    return CheckResult("india_eligible", a.eligible, a.detail, a.score)


def window_check(posting: JobPosting, cfg) -> tuple[CheckResult, WindowInfo]:
    """Judge the posting's window.

    A known out-of-window posting is a hard reject. A posting with no timing
    signal is never dropped: it passes the filter so it can be scored and shown,
    but unless ``allow_unknown_window`` is set it is only ever eligible for
    review, never for auto-apply (enforced at the apply boundary).
    """
    info = classify_window(posting.searchable_text(), cfg)
    if info.overlaps is True:
        return CheckResult("window", True, f"{info.detail} overlaps Jan-Jun", info.confidence), info
    if info.overlaps is False:
        return CheckResult("window", False, f"{info.detail} does not overlap Jan-Jun", 0.0), info
    if cfg.allow_unknown_window:
        return CheckResult("window", True, f"{info.detail}; unknown window allowed by config", 0.3), info
    return CheckResult(
        "window", True, f"{info.detail}; unknown window, eligible for review only", 0.0
    ), info


def filter_posting(posting: JobPosting, cfg) -> FilterResult:
    checks: list[CheckResult] = []
    reasons: list[str] = []

    checks.append(internship_check(posting, cfg))
    checks.append(fulltime_check(posting, cfg))
    checks.append(seniority_check(posting, cfg))
    checks.append(location_check(posting, cfg))
    win_check, info = window_check(posting, cfg)
    checks.append(win_check)

    for check in checks:
        if not check.passed:
            reasons.append(f"{check.name}: {check.detail}")

    return FilterResult(
        eligible=not reasons,
        checks=checks,
        window_label=info.label,
        window_confidence=info.confidence,
        reject_reasons=reasons,
    )
