"""Deterministic application lifecycle: outcomes, follow-ups and a stale sweep.

jobpilot's ``applications.outcome`` column was write-only. This module gives it
a single status vocabulary, computes which open applications have gone quiet,
and produces a plain follow-up template. No model is involved and nothing is
sent: a follow-up is text for the human to send themselves.

Rules (from the upstream study):

* **Open by exclusion.** A final outcome (``hired``, ``rejected``,
  ``no_response``, ``offer_declined``, ``withdrawn``) closes an application;
  everything else, including an empty value, stays open.
* **At most two follow-ups.** After the second silent follow-up the honest move
  is recording the resolution, not chasing a third time.
* **No new claims.** The template only names the role, the company and the
  submission date - facts already on record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from jobpilot.store import Store

VALID_OUTCOMES = (
    "applied",
    "interview",
    "offer",
    "hired",
    "rejected",
    "no_response",
    "offer_declined",
    "withdrawn",
)
FINAL_OUTCOMES = frozenset({"hired", "rejected", "no_response", "offer_declined", "withdrawn"})
OPEN_OUTCOMES = frozenset(VALID_OUTCOMES) - FINAL_OUTCOMES


def is_final(outcome) -> bool:
    return (outcome or "").strip().lower() in FINAL_OUTCOMES


def is_open(outcome) -> bool:
    return not is_final(outcome)


def normalize_outcome(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "_")


def _parse_when(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def quiet_days(row, *, today: date | None = None) -> int | None:
    """Days since the application's last activity, or ``None`` when undated.

    The most recent of the last follow-up, submission and last update counts, so
    logging a follow-up resets the clock.
    """
    today = today or date.today()
    stamps = [
        _parse_when(row["last_followup_at"]),
        _parse_when(row["submitted_at"]),
        _parse_when(row["updated_at"]),
    ]
    stamps = [stamp for stamp in stamps if stamp is not None]
    if not stamps:
        return None
    return (today - max(stamps).date()).days


@dataclass
class Candidate:
    app_id: int
    stable_id: str
    company: str
    title: str
    outcome: str
    status: str
    quiet_days: int
    reminders: int
    apply_url: str

    def row(self) -> tuple:
        return (
            self.app_id,
            self.company,
            self.title,
            self.outcome or self.status,
            self.quiet_days,
            self.reminders,
        )


def _tracked(row, approved: set[str]) -> bool:
    if is_final(row["outcome"]):
        return False
    return row["status"] == "submitted" or row["stable_id"] in approved


def _candidate(row, quiet: int) -> Candidate:
    return Candidate(
        app_id=int(row["id"]),
        stable_id=row["stable_id"],
        company=row["company"] or "",
        title=row["title"] or "",
        outcome=row["outcome"] or "",
        status=row["status"] or "",
        quiet_days=quiet,
        reminders=int(row["reminders"] or 0),
        apply_url=row["apply_url"] or "",
    )


def followup_candidates(
    store: Store,
    *,
    days: int = 10,
    max_reminders: int = 2,
    today: date | None = None,
) -> list[Candidate]:
    """Open, submitted/approved applications quiet for ``days`` with reminders left."""
    approved = store.approved_stable_ids()
    out: list[Candidate] = []
    for row in store.latest_applications():
        if not _tracked(row, approved):
            continue
        quiet = quiet_days(row, today=today)
        if quiet is None or quiet < int(days):
            continue
        if int(row["reminders"] or 0) >= int(max_reminders):
            continue
        out.append(_candidate(row, quiet))
    out.sort(key=lambda candidate: (-candidate.quiet_days, candidate.company.lower()))
    return out


def stale_candidates(
    store: Store,
    *,
    days: int = 60,
    today: date | None = None,
) -> list[Candidate]:
    """Open, submitted/approved applications quiet for ``days``."""
    approved = store.approved_stable_ids()
    out: list[Candidate] = []
    for row in store.latest_applications():
        if not _tracked(row, approved):
            continue
        quiet = quiet_days(row, today=today)
        if quiet is None or quiet < int(days):
            continue
        out.append(_candidate(row, quiet))
    out.sort(key=lambda candidate: (-candidate.quiet_days, candidate.company.lower()))
    return out


def candidate_for(store: Store, stable_id: str, *, today: date | None = None) -> Candidate | None:
    """Build a :class:`Candidate` for one posting's latest application."""
    row = store.latest_application(stable_id)
    if row is None:
        return None
    return _candidate(row, quiet_days(row, today=today) or 0)


def followup_template(candidate: Candidate) -> str:
    """A plain, claim-free follow-up draft for one application."""
    role = candidate.title or "the role"
    company = candidate.company or "your team"
    return (
        f"Subject: Following up on my {role} application\n\n"
        f"Dear {company} team,\n\n"
        f"I wanted to follow up on my application for the {role} role. "
        "I remain very interested in the position and would welcome the chance "
        "to discuss how I can contribute.\n\n"
        "Could you share any update on the timeline or next steps? "
        "I am happy to provide anything further that would help.\n\n"
        "Thank you for your time.\n\n"
        "Best regards,\n[your name]"
    )
