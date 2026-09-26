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
  falsy, or a past ``end_date``.

An *unknown* end date or absent registration metadata is **unverified**, not
closed: the posting stays open-but-unverified and is never dropped for missing
information. ``registerCount`` is never an automatic rejection - it is captured
elsewhere so the review page can warn ("N applicants") without capping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

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


@dataclass(frozen=True)
class OpenState:
    """The application's open state: ``True``, ``False``, or ``None`` if unverified."""

    open: bool | None = None
    reason: str = ""

    @property
    def closed(self) -> bool:
        return self.open is False


def _truthy(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in _FALSY


def assess_open_state(posting, *, today: date | None = None) -> OpenState:
    """Return whether the posting's application is open, closed, or unverified."""
    today = today or date.today()
    text = f"{posting.title or ''} {posting.description or ''}"
    if _CLOSED_TEXT_RE.search(text):
        return OpenState(False, "the posting states the application is closed")

    deadline = posting.deadline or extract_deadline(posting)
    if deadline_status(deadline, today=today) == "expired":
        return OpenState(False, f"the application deadline {deadline} has passed")

    raw = posting.raw if isinstance(posting.raw, dict) else {}
    # The typed registration fields arrive together on a real Unstop row. They
    # are judged only for an Unstop posting (or a row that explicitly carries
    # ``regn_open``), so another adapter's unrelated raw payload is never read as
    # registration metadata. A missing end date is unverified, not closed.
    unstop_typed = posting.source == "unstop" or "regn_open" in raw
    if "regn_open" in raw and not _truthy(raw.get("regn_open")):
        return OpenState(False, "registration is not open (regn_open is false)")
    if unstop_typed and "end_date" in raw:
        end_date = parse_iso_deadline(raw.get("end_date"))
        if end_date is not None and end_date < today:
            return OpenState(False, f"registration ended {end_date.isoformat()}")
    if unstop_typed and ("regn_open" in raw or "end_date" in raw):
        return OpenState(True, "")

    return OpenState(None, "")
