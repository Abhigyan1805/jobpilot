"""Operator-facing red-flag suggestions.

These are *suggestions for a human reviewer*, never facts, and they never alter
generated content. They are stored with the application record so the Captain
can see what looked risky at a glance. The advisor is deterministic: it needs no
model and no network, so it can never change a fact.
"""

from __future__ import annotations

from jobpilot.config import Config
from jobpilot.filtering import assess_location, is_internship
from jobpilot.models import JobPosting, MatchResult


def suggest_red_flags(posting: JobPosting, match: MatchResult, config: Config) -> list[str]:
    flags: list[str] = []
    loc = assess_location(posting, config.filter)
    if not loc.eligible:
        flags.append(f"location may not be open to India: {loc.detail}")
    if posting.is_remote is None and "remote" not in (posting.location or "").lower():
        flags.append("remote eligibility is not stated; confirm the work location")
    if not is_internship(posting, config.filter):
        flags.append("posting does not clearly read as an internship")
    if len(match.missing_keywords) >= 8:
        flags.append(
            f"JD asks for {len(match.missing_keywords)} skills absent from the profile; "
            "these are reported as gaps and were not inserted"
        )
    if match.coverage.ratio < 0.25 and (match.coverage.matched or match.coverage.missing):
        flags.append("low keyword coverage; the resume may not speak to this JD")
    if "unpaid" in posting.description.lower():
        flags.append("posting may be unpaid; confirm")
    return flags
