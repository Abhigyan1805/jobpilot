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


def _find(text: str, terms: list[str]) -> str | None:
    """Return the first term present in text as a whole phrase (word-bounded)."""
    low = (text or "").lower()
    for term in terms:
        if not term:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(term.lower().strip())}(?![a-z0-9])", low):
            return term
    return None


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
    haystack = f"{posting.title} {posting.employment_type}"
    hit = _find(haystack, cfg.fulltime_reject_keywords)
    if hit:
        return CheckResult("fulltime", False, f"full-time signal {hit!r}", 0.0)
    if _find(haystack, cfg.internship_keywords):
        return CheckResult("fulltime", True, "internship keyword present", 1.0)
    return CheckResult("fulltime", True, "no full-time signal", 0.5)


@dataclass
class LocationAssessment:
    score: float
    eligible: bool
    detail: str


def assess_location(posting: JobPosting, cfg) -> LocationAssessment:
    location = (posting.location or "").lower()
    desc = (posting.description or "").lower()
    combined = f"{location} {desc[:600]}"

    reject = _find(combined, cfg.location_reject_keywords)
    if reject:
        return LocationAssessment(0.0, False, f"location/work-authorization restriction: {reject!r}")

    if _find(location, cfg.india_keywords):
        return LocationAssessment(1.0, True, "location is in India")
    if _find(location, GLOBAL_TERMS):
        return LocationAssessment(0.95, True, "globally remote")
    if _find(combined, cfg.india_keywords):
        return LocationAssessment(0.9, True, "India mentioned in posting")

    remote = posting.is_remote is True or _find(location, cfg.remote_keywords) is not None
    abroad = _find(location, ABROAD_TERMS)
    if remote and not abroad:
        return LocationAssessment(0.85, True, "remote with no country restriction")
    if remote and abroad:
        if cfg.allow_onsite_abroad:
            return LocationAssessment(0.5, True, f"remote restricted to {abroad}, allowed by config")
        return LocationAssessment(0.1, False, f"remote restricted to non-India region {abroad!r}")

    if not location.strip():
        if getattr(cfg, "allow_unknown_location", False):
            return LocationAssessment(0.4, True, "location unspecified (allowed by config)")
        return LocationAssessment(0.0, False, "location unspecified")

    if abroad:
        if cfg.allow_onsite_abroad:
            return LocationAssessment(0.4, True, f"onsite abroad ({abroad}), allowed by config")
        return LocationAssessment(0.0, False, f"onsite location abroad ({abroad!r})")
    return LocationAssessment(0.2, False, f"location not confirmably open to India ({posting.location!r})")


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
