"""Deterministic stipend extraction and a monthly-floor classification.

The captain's rerun needs postings whose application is genuinely open *and*
whose stipend is at least a configured monthly amount. Stipend text in Indian
internship listings is inconsistent (``Stipend: INR 15,000-18,000/ month``,
``Stipend of ₹10,000``, ``Stipend range- Rs 5000 - Rs 10000``,
``Stipend: 3000 Per month``, ``1K``/``1.5K`` shorthand, bare ``INR 40000``), so
this module normalises it into one small enum instead of leaving each caller to
grep for its own pattern.

Assumptions (explicit):

* The parser is INR-only and monthly-by-design; ``[filter].stipend_floor`` is the
  only stipend knob. The floor is a *monthly* amount. A figure with no stated
  period is treated as monthly. An explicitly annual figure is divided by twelve;
  any other explicit period (per day/week/hour) cannot confirm a monthly floor
  and is left ``unstated`` rather than guessed at.
* A range is judged by its *lower* bound, so ``₹25,000-35,000`` does not clear a
  ₹30,000 floor. The upper bound is kept only for display, and a range is shown
  only when the text actually states one.
* The floor is judged against the posting's *governing* monthly stipend figure,
  not the minimum of every number in the text. A headcount, a benefit valued at
  an amount, a one-time bonus or an allowance is not the stipend base and never
  drags a qualifying figure below the floor.
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

#: States that must never appear on the main list.
DROPPED_STATES = frozenset({CONFIRMED_BELOW_FLOOR, UNPAID})

#: The parser recognises only the INR surface forms (``₹``/``Rs``/``INR``/
#: ``rupees``); a foreign-currency figure is never invented into rupees.
_CURRENCY = r"(?:₹|rs\.?|inr|rupees?)"
_MONTH_PERIOD = r"(?:per\s+month|/\s*months?\b|/\s*mo\b|monthly|p\.?m\.?\b|a\s+month|pcm)"
_YEAR_PERIOD = r"(?:per\s+(?:year|annum)|/\s*(?:year|annum)|yearly|annually)"
# LPA / "lakhs per annum" is an annual figure whose number is counted in lakhs.
_LPA_PERIOD = r"(?:lpa|lakhs?\s+(?:per\s+annum|p\.?a)|lakhs?\s*/\s*(?:year|annum))"

_AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?"

_MONEY_PREFIX_RE = re.compile(rf"{_CURRENCY}\s*{_AMOUNT}", re.IGNORECASE)
_MONEY_SUFFIX_RE = re.compile(rf"{_AMOUNT}\s*{_CURRENCY}(?![a-z])", re.IGNORECASE)
_MONEY_MONTH_RE = re.compile(rf"{_AMOUNT}\s*(?:/-)?\s*{_MONTH_PERIOD}", re.IGNORECASE)
_MONEY_YEAR_RE = re.compile(rf"{_AMOUNT}\s*(?:/-)?\s*{_YEAR_PERIOD}", re.IGNORECASE)
_MONEY_LPA_RE = re.compile(rf"{_AMOUNT}\s*{_LPA_PERIOD}\b", re.IGNORECASE)
# Bare shorthand ranges ("12-15k per month"): the K on the second number applies
# to the whole range, so both ends are thousands. An LPA range ("6-8 LPA") is the
# same idea with the lakh unit.
_RANGE_K_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)\s*([kK])\b",
    re.IGNORECASE,
)
_RANGE_LPA_RE = re.compile(
    rf"(\d[\d,]*(?:\.\d+)?)\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)\s*{_LPA_PERIOD}\b",
    re.IGNORECASE,
)
# A bare number only counts inside a clause that already talks about stipends.
_BARE_AMOUNT_RE = re.compile(rf"{_AMOUNT}", re.IGNORECASE)

#: A duration/percentage directly after a number makes it a term, not pay
#: ("3-month duration", "6 months", "3+ years", "rounds of interviews",
#: "10% commission").
_DURATION_AFTER_RE = re.compile(
    r"\s*\+?\s*[-–]?\s*(?:month|months|year|years|week|weeks|day|days|hour|hours"
    r"|percent|round|rounds)\b"
    r"|\s*%",
    re.IGNORECASE,
)

#: An explicit period after a figure decides whether it can be read as monthly.
#: Month/year slash forms are already consumed by the money patterns; this
#: catches a postposed ``per day``/``/week``/``an hour``, the adverb and
#: abbreviation surface forms (``hourly``/``hr``/``wk``) and ``p.a.``, so a
#: non-monthly rate is never silently treated as a floor-clearing monthly amount.
_AFTER_PERIOD_RE = re.compile(
    r"\s*(?:/-)?\s*(?:"
    r"(?:(?:per[-\s]+|/\s*|a\s+|an\s+)(?P<unit>months?|years?|annum|weeks?|days?|hours?|hrs?|wk|wks))\b"
    r"|(?P<word>monthly|yearly|annually|annual|hourly|daily|weekly|fortnightly)\b"
    r"|(?P<pa>p\.?\s*a\.?)(?![a-z])"
    r")",
    re.IGNORECASE,
)
#: A leading "annual"/"yearly" descriptor before a figure ("Annual stipend:
#: ₹3,00,000", "Stipend (annual): ₹3,00,000") marks the whole figure as yearly.
_PREPOSED_YEAR_RE = re.compile(r"\b(?:annual|yearly)\b", re.IGNORECASE)
_YEAR_UNITS = frozenset({"year", "years", "annum", "annual", "yearly", "annually"})
_MONTH_UNITS = frozenset({"month", "months", "monthly"})

#: A one-time total stated over a duration ("₹60,000 for 3 months") is a lump
#: sum, not a monthly figure: divide by the number of months to get the monthly
#: rate. A total over weeks/days has no monthly meaning, so the figure is not
#: read as monthly at all.
_LUMP_SUM_RE = re.compile(
    r"\s*(?:for|over|across)\s+(?P<n>\d{1,3})\s*(?P<unit>months?|weeks?|days?)\b",
    re.IGNORECASE,
)

#: A stated range joins two base figures with a connector. A range is shown only
#: when this connector actually appears between two collected figures; two
#: unrelated figures are never rendered as a low-high range.
_RANGE_BETWEEN_RE = re.compile(
    r"^\s*[kK]?\s*(?:[-–—]|to|through|till|until)\s*(?:(?:₹|rs\.?|inr|rupees?)\s*)?$",
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

#: Cue strength, used to pick the posting's governing figure: a figure tied to
#: the stipend itself outranks a figure tied to the broader pay package, which
#: outranks a figure with no pay cue at all. "CTC ₹6,00,000/annum. Stipend
#: ₹15,000/month." is a ₹15,000 stipend, not a ₹50,000 one.
_STRONG_CUE_RE = re.compile(r"\bstipend\b|\bremuneration\b", re.IGNORECASE)
_MEDIUM_CUE_RE = re.compile(r"\bsalary\b|\bcompensation\b|\bpay\b", re.IGNORECASE)

#: A figure in one of these contexts is not the stipend *base* and must never
#: drag a qualifying base below the floor: a headcount ("40 employees"), a
#: benefit valued at an amount ("training worth ₹10,000"), a one-time bonus, or
#: an allowance/reimbursement element.
_NONBASE_RE = re.compile(
    r"\b(?:employees?|staff|headcount|members?|people|clients?|customers?|users?)\b"
    r"|\bone[\s-]?time\b|\bone[\s-]?off\b|\bbonus\b|\ballowance\b|\breimburs\w*"
    r"|\bincentiv\w*|\bperks?\b|\bbene(?:fit|fits)\b|\bworth\b|\bvoucher\b"
    r"|\bprize\b|\baward\b|\bscholarship\b|\bfees?\b|\btuition\b"
    r"|\brelocation\b|\btravel\b|\bfood\b|\bmeals?\b|\baccommodation\b"
    r"|\binternet\b|\bcertificate\b",
    re.IGNORECASE,
)

#: Clause boundaries for context detection. A comma between digits is part of a
#: number ("15,000") and never splits; sentence punctuation only splits when
#: followed by whitespace so "Rs. 25,000" and "1.5K" stay whole. The additive
#: conjunctions split a clause too, so an add-on ("₹30,000/month plus a ₹5,000
#: bonus") cannot mark the base figure conditional or non-base.
_CLAUSE_BOUNDARY_RE = re.compile(
    r"[+;|\n]|(?<!\d),(?!\d)|(?<=[.!?])\s+|\b(?:and|with|plus)\b",
    re.IGNORECASE,
)


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


def _to_int(number: str, k_shorthand: str | None, multiplier: int = 1) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except (TypeError, ValueError):
        return None
    if k_shorthand:
        value *= 1000
    else:
        value *= multiplier
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
    nonbase: bool = False
    divisor: int = 1
    cue_rank: int = 0  # 2 stipend/remuneration, 1 salary/compensation/pay, 0 none

    @property
    def monthly(self) -> int:
        base = self.value // 12 if self.kind == "year" else self.value
        return base // self.divisor if self.divisor > 1 else base

    @property
    def is_base(self) -> bool:
        """A candidate for the posting's governing stipend figure."""
        return not self.conditional and not self.nonbase


def _clause_span(text: str, start: int) -> tuple[int, int]:
    """The bounds of the clause (``+``/``;``/``|``/newline/sentence/comma) around ``start``."""
    left = 0
    for boundary in _CLAUSE_BOUNDARY_RE.finditer(text, 0, start):
        left = boundary.end()
    following = _CLAUSE_BOUNDARY_RE.search(text, start)
    right = following.start() if following is not None else len(text)
    return left, right


def _is_conditional(clause: str) -> bool:
    return bool(_PERFORMANCE_RE.search(clause) or _CONDITIONAL_RE.search(clause))


def _is_nonbase(clause: str) -> bool:
    return bool(_NONBASE_RE.search(clause))


def _cue_rank(clause: str) -> int:
    if _STRONG_CUE_RE.search(clause):
        return 2
    if _MEDIUM_CUE_RE.search(clause):
        return 1
    return 0


def _overlaps(covered: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < c_end and end > c_start for c_start, c_end in covered)


def _period_after(text: str, pos: int) -> str | None:
    """The kind of period stated right after ``pos``: month, year or other."""
    match = _AFTER_PERIOD_RE.match(text, pos)
    if match is None:
        return None
    if match.group("pa"):
        return "year"
    unit = (match.group("unit") or match.group("word") or "").casefold()
    if unit in _YEAR_UNITS:
        return "year"
    if unit in _MONTH_UNITS:
        return "month"
    return "other"


def _add(
    amounts: list[_Amount],
    covered: list[tuple[int, int]],
    text: str,
    match: re.Match,
    *,
    kind: str,
    multiplier: int = 1,
    bare: bool = False,
    lump_ok: bool = False,
) -> None:
    if _overlaps(covered, match.start(), match.end()):
        return
    number = match.group(1)
    shorthand = match.group(2) if match.lastindex and match.lastindex >= 2 else None
    value = _to_int(number, shorthand, multiplier)
    if value is None:
        return
    start, end = match.start(1), match.end(1)
    if _DURATION_AFTER_RE.match(text, end):
        return
    # A *bare* four-digit year near a stipend is not a stipend; an explicit
    # currency/period/prefixed amount is never discarded this way. Guard on the
    # parsed value, not the raw token, so a trailing comma ("2015,") is handled.
    if bare and not shorthand and re.fullmatch(r"(?:19|20)\d{2}", number.replace(",", "").strip()):
        return
    period = _period_after(text, match.end())
    if period == "other":
        return
    if period == "year":
        kind = "year"
    # A bare number only counts when its own clause talks about stipends; a
    # number in a neighbouring clause (experience, headcount, a PIN code) is not
    # the stipend and must never drag the governing figure below the floor.
    clause_left, clause_right = _clause_span(text, start)
    clause = text[clause_left:clause_right]
    if bare and not _CUE_RE.search(clause):
        return
    if period is None and _PREPOSED_YEAR_RE.search(text[clause_left:start]):
        kind = "year"
    divisor = 1
    if lump_ok and period is None:
        lump = _LUMP_SUM_RE.match(text, match.end())
        if lump is not None:
            if not lump.group("unit").casefold().startswith("month"):
                return
            divisor = max(1, int(lump.group("n")))
    amounts.append(
        _Amount(
            start=start,
            end=end,
            value=value,
            kind=kind,
            conditional=_is_conditional(clause),
            nonbase=_is_nonbase(clause),
            divisor=divisor,
            cue_rank=_cue_rank(clause),
        )
    )
    covered.append((match.start(), match.end()))


def _add_range(
    amounts: list[_Amount],
    covered: list[tuple[int, int]],
    text: str,
    match: re.Match,
    *,
    multiplier: int,
    kind: str,
    value_groups: tuple[int, int] = (1, 2),
) -> None:
    """Record both ends of a shorthand range whose unit applies to both numbers."""
    if _overlaps(covered, match.start(), match.end()):
        return
    period = _period_after(text, match.end())
    if period == "other":
        return
    if period == "year":
        kind = "year"
    clause_left, clause_right = _clause_span(text, match.start(value_groups[0]))
    clause = text[clause_left:clause_right]
    if period is None and _PREPOSED_YEAR_RE.search(text[clause_left:match.start(value_groups[0])]):
        kind = "year"
    for group_start in value_groups:
        number = match.group(group_start)
        value = _to_int(number, None, multiplier)
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
                kind=kind,
                conditional=_is_conditional(clause),
                nonbase=_is_nonbase(clause),
                cue_rank=_cue_rank(clause),
            )
        )
    covered.append((match.start(), match.end()))


def _collect_amounts(text: str) -> list[_Amount]:
    amounts: list[_Amount] = []
    covered: list[tuple[int, int]] = []
    for match in _RANGE_K_RE.finditer(text):
        _add_range(
            amounts, covered, text, match, multiplier=1000, kind="month", value_groups=(1, 3)
        )
    for match in _RANGE_LPA_RE.finditer(text):
        _add_range(amounts, covered, text, match, multiplier=100_000, kind="year")
    for match in _MONEY_MONTH_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month")
    for match in _MONEY_YEAR_RE.finditer(text):
        _add(amounts, covered, text, match, kind="year")
    for match in _MONEY_LPA_RE.finditer(text):
        _add(amounts, covered, text, match, kind="year", multiplier=100_000)
    for match in _MONEY_PREFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", lump_ok=True)
    for match in _MONEY_SUFFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", lump_ok=True)
    # Bare numbers count only when they sit in stipend context and do not
    # overlap an amount already found by a currency/period pattern.
    for match in _BARE_AMOUNT_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", bare=True, lump_ok=True)
    return amounts


def classify_stipend(
    text: str,
    *,
    floor: int = DEFAULT_FLOOR,
) -> StipendInfo:
    """Classify a posting's stipend text against a monthly floor.

    Only the INR surface forms (``₹``/``Rs``/``INR``/``rupees``) are recognised;
    a foreign-currency figure is never invented into rupees.
    """
    text = text or ""
    amounts = _collect_amounts(text)
    # Judge the floor against the posting's governing stipend figure - the
    # recurring/fixed amount tied to a stipend cue - never against min() of
    # unrelated numbers (headcount, a benefit's worth, a one-time bonus or an
    # allowance), which must not drag a qualifying base below the floor.
    base = [a for a in amounts if a.is_base]
    if base:
        groups: dict[int, list[_Amount]] = {}
        for amount in base:
            groups.setdefault(amount.cue_rank, []).append(amount)
        ordered = sorted(groups[max(groups)], key=lambda a: a.start)
        pairs = [
            (ordered[i], ordered[i + 1])
            for i in range(len(ordered) - 1)
            if _RANGE_BETWEEN_RE.match(text[ordered[i].end : ordered[i + 1].start])
        ]
        if pairs:
            low = min(pairs[0][0].monthly, pairs[0][1].monthly)
            high = max(pairs[0][0].monthly, pairs[0][1].monthly)
        else:
            low = high = ordered[0].monthly
        state = CONFIRMED_GE_FLOOR if low >= int(floor) else CONFIRMED_BELOW_FLOOR
        return StipendInfo(
            state=state,
            amount=low,
            amount_high=high,
            note="confirmed monthly figure",
        )

    if _UNPAID_RE.search(text):
        return StipendInfo(state=UNPAID, note="the posting states there is no fixed paid stipend")
    if amounts and all(a.conditional for a in amounts):
        return StipendInfo(state=UNPAID, note="pay is performance-based or conditional")
    if _PERFORMANCE_RE.search(text):
        return StipendInfo(state=UNPAID, note="performance-based or commission-only pay")
    if _CUE_RE.search(text):
        return _unstated("a stipend is mentioned without a fixed figure")
    return _unstated("no stipend stated")
