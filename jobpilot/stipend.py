"""Deterministic stipend extraction and a monthly-floor classification.

The captain's rerun needs postings whose application is genuinely open *and*
whose stipend is at least a configured monthly amount. Stipend text in Indian
internship listings is inconsistent (``Stipend: INR 15,000-18,000/ month``,
``Stipend of ₹10,000``, ``Stipend range- Rs 5000 - Rs 10000``,
``Stipend: 3000 Per month``, ``1K``/``1.5K`` shorthand, bare ``INR 40000``), so
this module normalises it into one small enum instead of leaving each caller to
grep for its own pattern.

Assumptions (explicit, and configurable through ``[filter]``):

* The floor is a *monthly* amount and the default currency is INR. A figure
  with no stated period is treated as monthly. An explicitly annual figure is
  divided by twelve; any other explicit period (per day/week/hour) cannot
  confirm a monthly floor and is left ``unstated`` rather than guessed at.
* A range is judged by its *lower* bound, so ``₹25,000-35,000`` does not clear a
  ₹30,000 floor. The upper bound is kept only for display.
* ``unpaid`` covers the clearly non-fixed forms (``Unpaid``,
  ``Performance-based``, ``commission only``, ``no fixed stipend``). A posting
  that merely *mentions* a stipend without a figure (``Stipend:``,
  ``stipend will be provided``, ``stipend is negotiable``) is ``unstated`` and,
  per the captain's choice, is surfaced in a separate section instead of being
  dropped - a missing amount is never invented and never silently fails.

Nothing here scores, ranks or invents: it only classifies text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Confirmed monthly amount at or above the floor: shown in the main list.
CONFIRMED_GE_FLOOR = "confirmed_ge_floor"
#: Confirmed monthly amount below the floor: dropped.
CONFIRMED_BELOW_FLOOR = "confirmed_below_floor"
#: No fixed/paid stipend (explicitly unpaid or performance/commission only): dropped.
UNPAID = "unpaid"
#: A stipend is mentioned or absent but no figure is stated: shown separately.
UNSTATED = "unstated"

DEFAULT_FLOOR = 30000
DEFAULT_CURRENCY = "INR"

#: States that must never appear on the main list.
DROPPED_STATES = frozenset({CONFIRMED_BELOW_FLOOR, UNPAID})

_CURRENCY = r"(?:₹|rs\.?|inr|rupees?)"
_MONTH_PERIOD = r"(?:per\s+month|/\s*months?\b|/\s*mo\b|monthly|p\.?m\.?\b|a\s+month|pcm)"
_YEAR_PERIOD = r"(?:per\s+(?:year|annum)|/\s*(?:year|annum)|yearly|annually|lpa|per\s+annum)"

_AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?"

_MONEY_PREFIX_RE = re.compile(rf"{_CURRENCY}\s*{_AMOUNT}", re.IGNORECASE)
_MONEY_SUFFIX_RE = re.compile(rf"{_AMOUNT}\s*{_CURRENCY}(?![a-z])", re.IGNORECASE)
_MONEY_MONTH_RE = re.compile(rf"{_AMOUNT}\s*(?:/-)?\s*{_MONTH_PERIOD}", re.IGNORECASE)
_MONEY_YEAR_RE = re.compile(rf"{_AMOUNT}\s*(?:/-)?\s*{_YEAR_PERIOD}", re.IGNORECASE)
# Bare shorthand ranges ("12-15k per month"): the K on the second number applies
# to the whole range, so both ends are thousands.
_RANGE_K_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)\s*[kK]\b",
    re.IGNORECASE,
)
# A bare number only counts inside a clause that already talks about stipends.
_BARE_AMOUNT_RE = re.compile(rf"{_AMOUNT}", re.IGNORECASE)

#: A duration/percentage directly after a number makes it a term, not pay
#: ("3-month duration", "6 months", "10% commission").
_DURATION_AFTER_RE = re.compile(
    r"\s*[-–]?\s*(?:month|months|year|years|week|weeks|day|days|hour|hours|percent)\b"
    r"|\s*%",
    re.IGNORECASE,
)

#: Unambiguously no fixed paid stipend.
_UNPAID_RE = re.compile(
    r"\bunpaid\b"
    r"|\bno\s+stipend\b"
    r"|\bwithout\s+(?:a\s+)?stipend\b"
    r"|\bno\s+fixed\s+stipend\b"
    r"|\bnot\s+paid\b"
    r"|\bcommission[\s-]?only\b"
    r"|\bonly\s+commission\b",
    re.IGNORECASE,
)

#: Pay that exists but is not a fixed monthly figure.
_PERFORMANCE_RE = re.compile(
    r"performance[\s-]?based"
    r"|based\s+on\s+performance"
    r"|\bperformance\s+stipend\b"
    r"|\bvariable\s+(?:stipend|pay|component)\b"
    r"|\bincentiv(?:e|es)\b",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(r"\bup\s*to\b", re.IGNORECASE)

#: Words that put a bare number "in stipend context".
_CUE_RE = re.compile(
    r"\bstipend\b|\bsalary\b|\bremuneration\b|\bcompensation\b|\bpay\b",
    re.IGNORECASE,
)

_CUE_WINDOW = 60
_CONDITIONAL_WINDOW = 25


@dataclass(frozen=True)
class StipendInfo:
    """The classification of one posting's stipend text."""

    state: str = UNSTATED
    amount: int | None = None
    amount_high: int | None = None
    note: str = ""
    period: str = "month"

    @property
    def confirmed(self) -> bool:
        return self.state in (CONFIRMED_GE_FLOOR, CONFIRMED_BELOW_FLOOR)

    @property
    def dropped(self) -> bool:
        return self.state in DROPPED_STATES

    def display_label(self) -> str:
        """A short human label, e.g. ``₹40,000/mo confirmed`` or ``stipend not stated``."""
        if self.state == UNSTATED:
            return "stipend not stated"
        if self.state == UNPAID:
            return "unpaid / no fixed stipend"
        amount = self.amount or 0
        if self.amount_high and self.amount_high != amount:
            shown = f"₹{amount:,}-{self.amount_high:,}/mo"
        else:
            shown = f"₹{amount:,}/mo"
        return f"{shown} confirmed" if self.state == CONFIRMED_GE_FLOOR else f"{shown} below floor"


def _unstated(note: str = "") -> StipendInfo:
    return StipendInfo(state=UNSTATED, note=note)


def _to_int(number: str, k_shorthand: str | None) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except (TypeError, ValueError):
        return None
    if k_shorthand:
        value *= 1000
    value = int(round(value))
    if value <= 0 or value > 10_000_000:
        return None
    return value


@dataclass(frozen=True)
class _Amount:
    start: int
    end: int
    value: int
    kind: str = "month"  # "month" or "year"
    conditional: bool = False

    @property
    def monthly(self) -> int:
        return self.value // 12 if self.kind == "year" else self.value


def _has_cue(text: str, pos: int) -> bool:
    window = text[max(0, pos - _CUE_WINDOW): pos + _CUE_WINDOW]
    return bool(_CUE_RE.search(window))


def _is_conditional(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - _CONDITIONAL_WINDOW): end + _CONDITIONAL_WINDOW]
    return bool(_PERFORMANCE_RE.search(window) or _CONDITIONAL_RE.search(window))


def _add(
    amounts: list[_Amount],
    covered: list[tuple[int, int]],
    text: str,
    match: re.Match,
    *,
    kind: str,
) -> None:
    number = match.group(1)
    shorthand = match.group(2) if match.lastindex and match.lastindex >= 2 else None
    value = _to_int(number, shorthand)
    if value is None:
        return
    start, end = match.start(1), match.end(1)
    if _DURATION_AFTER_RE.match(text, end):
        return
    # A bare four-digit year near a stipend is not a stipend.
    if not shorthand and "," not in number and re.fullmatch(r"(?:19|20)\d{2}", number):
        return
    amounts.append(
        _Amount(
            start=start,
            end=end,
            value=value,
            kind=kind,
            conditional=_is_conditional(text, start, end),
        )
    )
    covered.append((match.start(), match.end()))


def _add_range(
    amounts: list[_Amount],
    covered: list[tuple[int, int]],
    text: str,
    match: re.Match,
) -> None:
    """Record both ends of a shorthand range whose K marks both numbers."""
    for group_start in (1, 2):
        number = match.group(group_start)
        value = _to_int(number, "k")
        if value is None:
            continue
        start, end = match.start(group_start), match.end(group_start)
        if _DURATION_AFTER_RE.match(text, end):
            continue
        amounts.append(
            _Amount(
                start=start,
                end=end,
                value=value,
                kind="month",
                conditional=_is_conditional(text, start, end),
            )
        )
    covered.append((match.start(), match.end()))


def _collect_amounts(text: str) -> list[_Amount]:
    amounts: list[_Amount] = []
    covered: list[tuple[int, int]] = []
    for match in _RANGE_K_RE.finditer(text):
        _add_range(amounts, covered, text, match)
    for match in _MONEY_MONTH_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month")
    for match in _MONEY_YEAR_RE.finditer(text):
        _add(amounts, covered, text, match, kind="year")
    for match in _MONEY_PREFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month")
    for match in _MONEY_SUFFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month")
    # Bare numbers count only when they sit in stipend context and do not
    # overlap an amount already found by a currency/period pattern.
    for match in _BARE_AMOUNT_RE.finditer(text):
        start, end = match.start(), match.end()
        if any(start < c_end and end > c_start for c_start, c_end in covered):
            continue
        if not _has_cue(text, start):
            continue
        _add(amounts, covered, text, match, kind="month")
    return amounts


def classify_stipend(
    text: str,
    *,
    floor: int = DEFAULT_FLOOR,
    currency: str = DEFAULT_CURRENCY,
) -> StipendInfo:
    """Classify a posting's stipend text against a monthly floor.

    ``currency`` is documented for callers/config but the parser only recognises
    the INR surface forms (``₹``/``Rs``/``INR``/``rupees``); a foreign-currency
    figure is not invented into rupees.
    """
    del currency  # recognised surface forms are INR-only by design
    text = text or ""
    if _UNPAID_RE.search(text):
        return StipendInfo(state=UNPAID, note="the posting states there is no fixed paid stipend")

    amounts = _collect_amounts(text)
    clean = [a for a in amounts if not a.conditional]
    if clean:
        values = [a.monthly for a in clean]
        low, high = min(values), max(values)
        state = CONFIRMED_GE_FLOOR if low >= int(floor) else CONFIRMED_BELOW_FLOOR
        return StipendInfo(
            state=state,
            amount=low,
            amount_high=high,
            note="confirmed monthly figure",
        )

    if amounts and all(a.conditional for a in amounts):
        return StipendInfo(state=UNPAID, note="pay is performance-based or conditional")
    if _PERFORMANCE_RE.search(text):
        return StipendInfo(state=UNPAID, note="performance-based or commission-only pay")
    if _CUE_RE.search(text):
        return _unstated("a stipend is mentioned without a fixed figure")
    return _unstated("no stipend stated")
