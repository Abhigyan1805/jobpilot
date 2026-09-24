"""Extract and interpret an application deadline from a posting.

Internship deadlines are decision-critical and jobpilot previously ignored them.
This module extracts a deadline only where the posting states one next to an
application cue ("apply by", "application deadline", "applications close", ...),
stores it as an ISO date, and derives a display status (closing soon / expired)
and a staleness flag from the published date.

Two rules from the upstream study are honoured:

* **A defensive parser that never guesses.** Only unambiguous date forms are
  accepted (ISO and month-name dates); a bare or ambiguous numeric date is
  ignored. A stored value that is not a valid ISO date is treated exactly like
  an absent one.
* **Absence is not a correction.** A posting with no stated deadline keeps no
  deadline and its status is never changed by one.

The deadline is deliberately *not* a hard filter: an expired posting is surfaced
as expired but never dropped, and a deadline is never confused with the
internship's own start/end window (which the structural window classifier owns).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from jobpilot.models import JobPosting

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

# Phrases that introduce the *application* deadline, never the internship window.
# These are explicit: an explicit application cue always outranks the generic
# closure cue below.
_APPLICATION_CUE_RE = re.compile(
    r"(?:"
    r"appl(?:y|ies|ication|ications)\s+(?:by|before|no\s+later\s+than)"
    r"|deadline(?:\s+(?:for|to)\s+apply(?:ing)?)?"
    r"|last\s+date\s+(?:to\s+apply|of\s+application|for\s+application)"
    r"|applications?\s+(?:close|closes|closing|are\s+closed)"
    r"|applications?\s+(?:are\s+)?(?:accepted|open|available)"
    r"|(?:accepted|open|available)\s+(?:until|till|through|up\s+to)"
    r")",
    re.IGNORECASE,
)
# A generic closure phrase ("the office closes on ..."). It is only consulted
# when no explicit application cue yielded a date, so it cannot report a
# non-application closure as the deadline.
_GENERIC_CUE_RE = re.compile(r"closes?\s+(?:on|by)", re.IGNORECASE)
_ISO_RE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
_MONTH_FIRST_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
_DAY_FIRST_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
# A connector that directly joins two dates states a range ("A to B"); only then
# is the later date the deadline. Any intervening words break the range.
_RANGE_CONNECTOR_RE = re.compile(r"\s*(?:-|–|—|through|until|till|to)\s*", re.IGNORECASE)
# How far after a cue to look for its date.
_LOOKAHEAD = 90


def parse_iso_deadline(value) -> date | None:
    """Defensively parse a stored deadline: only a real ``YYYY-MM-DD`` counts.

    Anything else (``"ASAP"``, ``"15.03.2026"``, free text, a non-string) is
    treated exactly like an absent value - never compared, never guessed at.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _date_candidates(window: str) -> list[tuple[int, int, date]]:
    candidates: list[tuple[int, int, date]] = []
    for match in _ISO_RE.finditer(window):
        try:
            candidates.append(
                (match.start(), match.end(), date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
            )
        except ValueError:
            continue
    for match in _MONTH_FIRST_RE.finditer(window):
        month = MONTHS.get(match.group(1).lower())
        if not month:
            continue
        try:
            candidates.append(
                (match.start(), match.end(), date(int(match.group(3)), month, int(match.group(2))))
            )
        except ValueError:
            continue
    for match in _DAY_FIRST_RE.finditer(window):
        month = MONTHS.get(match.group(2).lower())
        if not month:
            continue
        try:
            candidates.append(
                (match.start(), match.end(), date(int(match.group(3)), month, int(match.group(1))))
            )
        except ValueError:
            continue
    candidates.sort(key=lambda item: item[0])
    return candidates


def _pick(candidates: list[tuple[int, int, date]], window: str) -> date | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][2]
    first, last = candidates[0], candidates[-1]
    between = window[first[1]: last[0]]
    # Only a connector that directly joins the two dates is a range ("A to B");
    # a sentence or extra words in between (an internship window) is not.
    if _RANGE_CONNECTOR_RE.fullmatch(between):
        return last[2]
    return first[2]


def extract_deadline(posting: JobPosting) -> str:
    """Return the posting's stated application deadline as ``YYYY-MM-DD`` or ``""``.

    The cue phrase must be present, so a bare date in the body (an internship
    start/end window, a posted date) is never mistaken for a deadline. An
    explicit application cue is tried first; the generic closure cue is only a
    fallback. A cue with no unambiguous date after it yields no deadline rather
    than a guess.
    """
    text = " ".join(part for part in [posting.description, posting.title] if part)
    if not text:
        return ""
    for cue_re in (_APPLICATION_CUE_RE, _GENERIC_CUE_RE):
        for cue in cue_re.finditer(text):
            window = text[cue.end(): cue.end() + _LOOKAHEAD]
            chosen = _pick(_date_candidates(window), window)
            if chosen is not None:
                return chosen.isoformat()
    return ""


def deadline_status(
    deadline,
    *,
    today: date | None = None,
    closing_soon_days: int = 7,
) -> str:
    """``"expired"``, ``"closing_soon"``, ``"open"`` or ``""`` for a stored deadline."""
    parsed = parse_iso_deadline(deadline)
    if parsed is None:
        return ""
    today = today or date.today()
    if parsed < today:
        return "expired"
    if (parsed - today).days <= int(closing_soon_days):
        return "closing_soon"
    return "open"


def published_date(published_at) -> date | None:
    """Parse a published timestamp (ISO datetime or unix seconds) into a date."""
    if published_at in (None, ""):
        return None
    text = str(published_at).strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def staleness_days(published_at, *, today: date | None = None) -> int | None:
    """Days since the posting was published, or ``None`` when unparseable."""
    parsed = published_date(published_at)
    if parsed is None:
        return None
    today = today or date.today()
    return (today - parsed).days


def is_stale(published_at, *, today: date | None = None, stale_days: int = 30) -> bool:
    age = staleness_days(published_at, today=today)
    return age is not None and age > int(stale_days)


def format_deadline(
    deadline,
    *,
    today: date | None = None,
    closing_soon_days: int = 7,
) -> str:
    """A short human label for a stored deadline, e.g. ``2026-03-15 (closing soon)``."""
    if not parse_iso_deadline(deadline):
        return ""
    status = deadline_status(deadline, today=today, closing_soon_days=closing_soon_days)
    label = {"expired": "expired", "closing_soon": "closing soon", "open": "open"}.get(status, "")
    return f"{deadline} ({label})" if label else str(deadline)
