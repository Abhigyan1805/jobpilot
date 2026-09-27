"""Decide whether a posting's application is actually open.

Unstop's search rows are unreliable on their own: a row can be ``status="LIVE"``
while the application is already closed. Live probes on 2026-09-26 returned
postings with ``end_date`` in January, July and August 2026 still marked
``LIVE`` and ``regn_open=1`` - the "Application Closed" links the captain hit.

This module makes one real open-state decision, shared by every adapter through
the hard filter, from signals that are already present on the posting:

* an explicit closed statement in the posting text ("application closed",
  "applications closed", "no longer accepting");
* a stated application deadline that has passed (reusing
  :mod:`jobpilot.deadline`, never a parallel date parser);
* Unstop's typed registration metadata when the row carries it: ``regn_open``
  falsy, a past registration close, or a past ``end_date``.

Unstop marks rows ``status="LIVE"`` and ``regn_open=1`` long after the
application has closed, so those two fields alone are not trusted. The
authoritative close is the registration window Unstop returns separately from
the internship window: ``regnRequirements.end_regn_dt`` (the date registrations
stop) and ``regnRequirements.start_regn_dt`` (the date they open). A row whose
registration window has closed is rejected even while ``status`` stays ``LIVE``.
This is what caught the page-19 misses: Deep Variance, Prism Labs, Kisan Udyog
and Zenotalent all carried a future-looking ``end_date`` (the internship end) but
a past ``end_regn_dt``.

An *unknown* end date or absent registration metadata is **unverified**, not
closed: the source published no closure signal. It stays open-but-unverified so
the pipeline can still surface it, and ``jobpilot present`` marks it as
unverified rather than silently presenting it as confirmed-open. An applicant
count is not an open-state signal at all: the tool never reads it, so volume can
never silently close a posting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from jobpilot.deadline import deadline_status, extract_deadline, parse_iso_deadline

#: Phrases that state the application itself is closed.
_CLOSED_TEXT_RE = re.compile(
    r"applications?\s+(?:are\s+|is\s+)?(?:now\s+|already\s+)?closed\b"
    r"|applications?\s+closed\b"
    r"|applications?\s+(?:are\s+)?no\s+longer\s+(?:being\s+)?accepted\b"
    r"|no\s+longer\s+accepting\b"
    r"|registration\s+(?:is\s+)?closed\b",
    re.IGNORECASE,
)

#: String values Unstop uses for a falsy boolean.
_FALSY = {"", "0", "false", "no", "none", "null"}

#: An ISO date or datetime, used for Unstop's registration window. The time is
#: kept when the board states one (a registration close earlier *today* has
#: passed), while a date-only value is compared at midnight.
_ISO_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?"
)


def _parse_registration_dt(value) -> datetime | None:
    """Parse Unstop's registration-window timestamp, keeping any time of day."""
    if not isinstance(value, str):
        return None
    match = _ISO_DATETIME_RE.match(value.strip())
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4) or 0),
            int(match.group(5) or 0),
            int(match.group(6) or 0),
        )
    except ValueError:
        return None


@dataclass(frozen=True)
class OpenState:
    """The application's open state: ``True``, ``False``, or ``None`` if unverified."""

    open: bool | None = None
    reason: str = ""

    @property
    def closed(self) -> bool:
        return self.open is False

    @property
    def key(self) -> str:
        """A short stable key for persisting: ``open``, ``closed`` or ``unverified``."""
        if self.open is True:
            return "open"
        if self.open is False:
            return "closed"
        return "unverified"


def _truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in _FALSY


def _registration_window(raw: dict) -> tuple:
    """Unstop's registration open/close dates, from the flat or nested payload.

    Unstop's search row carries the real application window under
    ``regnRequirements`` (``start_regn_dt``/``end_regn_dt``), separate from the
    top-level ``start_date``/``end_date`` (the internship's own window). Both
    spellings are accepted so a row with either layout is read.
    """
    nested = raw.get("regnRequirements")
    nested = nested if isinstance(nested, dict) else {}
    start = raw.get("start_regn_dt") or nested.get("start_regn_dt")
    end = raw.get("end_regn_dt") or nested.get("end_regn_dt")
    return _parse_registration_dt(start), _parse_registration_dt(end)


def assess_open_state(posting, *, today: date | None = None, now: datetime | None = None) -> OpenState:
    """Return whether the posting's application is open, closed, or unverified."""
    if now is None:
        now = datetime.combine(today, time.min) if today is not None else datetime.now()
    today = today or now.date()
    text = f"{posting.title or ''} {posting.description or ''}"
    if _CLOSED_TEXT_RE.search(text):
        return OpenState(False, "the posting states the application is closed")

    deadline = posting.deadline or extract_deadline(posting)
    if deadline_status(deadline, today=today) == "expired":
        return OpenState(False, f"the application deadline {deadline} has passed")

    raw = posting.raw if isinstance(posting.raw, dict) else {}
    # The typed registration fields arrive together on a real Unstop row. They
    # are judged only for an Unstop posting (or a row that explicitly carries a
    # registration field), so another adapter's unrelated raw payload is never
    # read as registration metadata. A missing window is unverified, not closed.
    unstop_typed = posting.source == "unstop" or any(
        key in raw for key in ("regn_open", "end_regn_dt", "start_regn_dt", "regnRequirements")
    )
    if "regn_open" in raw and not _truthy(raw.get("regn_open")):
        return OpenState(False, "registration is not open (regn_open is false)")

    regn_start, regn_end = _registration_window(raw)
    if unstop_typed and regn_end is not None and regn_end < now:
        return OpenState(False, f"registration closed {regn_end.isoformat()}")
    if unstop_typed and regn_start is not None and regn_start > now:
        return OpenState(False, f"registration opens later ({regn_start.isoformat()})")
    if unstop_typed and "end_date" in raw:
        end_date = parse_iso_deadline(raw.get("end_date"))
        if end_date is not None and end_date < today:
            return OpenState(False, f"registration ended {end_date.isoformat()}")
    if unstop_typed and any(
        key in raw for key in ("regn_open", "end_date", "end_regn_dt", "start_regn_dt", "regnRequirements")
    ):
        return OpenState(True, "")

    return OpenState(None, "")
