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
* ``unpaid`` covers only the explicit non-fixed forms (``Unpaid``,
  ``no stipend``, ``not paid``, ``commission only``). A posting that merely
  *mentions* a stipend, conditions it on performance, or quotes an ``up to``
  cap without a fixed figure (``Stipend:``, ``stipend will be provided``,
  ``based on performance``, ``up to ₹50,000/month``) is ``unstated`` and, per
  the captain's choice, is surfaced in a separate section instead of being
  dropped - a missing amount is never invented and never silently fails.
* The parser reads only rupee postings: the text must carry an INR marker
  (``₹``/``Rs``/``INR``/``rupees``) somewhere, and a figure explicitly quoted in
  another currency (``$``/``USD``/``EUR``/...) is never counted. A posting with
  no rupee marker at all is left ``unstated`` rather than judged against the ₹
  floor or displayed as rupees - the parser never invents rupees.
* A non-stipend package figure (``CTC``, ``salary package``, ``total
  compensation``) is never the stipend base and must never confirm the floor: a
  package is not a stipend.

Nothing here scores, ranks or invents: it only classifies text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Confirmed monthly amount at or above the floor: shown in the main list.
CONFIRMED_GE_FLOOR = "confirmed_ge_floor"
#: Confirmed monthly amount below the floor: dropped.
CONFIRMED_BELOW_FLOOR = "confirmed_below_floor"
#: No fixed/paid stipend (explicitly unpaid or commission only): dropped.
UNPAID = "unpaid"
#: A stipend is mentioned or absent but no figure is stated: shown separately.
UNSTATED = "unstated"

DEFAULT_FLOOR = 30000

#: States that must never appear on the main list.
DROPPED_STATES = frozenset({CONFIRMED_BELOW_FLOOR, UNPAID})

#: The parser recognises only the INR surface forms (``₹``/``Rs``/``INR``/
#: ``rupees``); a foreign-currency figure is never invented into rupees.
_CURRENCY = r"(?:₹|rs\.?|inr|rupees?)"
_MONTH_PERIOD = r"(?:per\s+month|/\s*months?\b|/\s*mo\b|monthly|a\s+month|pcm)"
_YEAR_PERIOD = r"(?:per\s+(?:year|annum)|/\s*(?:year|annum)|yearly|annually)"
# LPA / "lakhs per annum" is an annual figure whose number is counted in lakhs.
_LPA_PERIOD = r"(?:lpa|lakhs?\s+(?:per\s+annum|p\.?a)|lakhs?\s*/\s*(?:year|annum))"

_AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*([kK]\b|[lL](?:akhs?|acs?)?\b)?"

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
    r"(?:(?:per[-\s]+|/\s*|a\s+|an\s+)(?P<unit>months?|years?|annum|weeks?|days?"
    r"|hours?|hrs?|wk|wks|quarters?|fortnights?|bi[-\s]?weeks?))\b"
    r"|(?P<word>monthly|yearly|annually|annual|hourly|daily|weekly|fortnightly"
    r"|quarterly|biweekly|bi-weekly)\b"
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
#: A range's period is stated once, at its far end ("₹30,000-40,000 per hour").
#: The lower end carries no period of its own, so it must adopt the range's.
_RANGE_TAIL_RE = re.compile(
    r"\s*(?:[-–—]|to|through|till|until)\s*"
    rf"(?:(?:₹|rs\.?|inr|rupees?)\s*)?{_AMOUNT}",
    re.IGNORECASE,
)

#: A bare lakh unit after a number scales it to lakhs (×100000). Unlike the
#: month-scale ``k`` shorthand a lakh figure with no stated period is the annual
#: package, so it is divided by twelve.
_LAKH_UNITS = frozenset({"l", "lac", "lacs", "lakh", "lakhs"})

#: The parser is INR-only: an amount is read only in a rupee posting (one that
#: carries an INR marker). The symbol needs no word boundary; the look-behind
#: keeps the ``rs`` inside a word (``hours``) from counting as a marker.
_INR_RE = re.compile(r"₹|(?<![a-z0-9])(?:inr|rs\.?|rupees?)", re.IGNORECASE)

#: Non-INR currency surface forms. An amount quoted in one of these is not an
#: INR figure even in a posting that also quotes rupees.
_FOREIGN_SYMBOLS = frozenset("$£€¥₽₩")
_FOREIGN_CODES = frozenset(
    {
        "usd", "eur", "gbp", "aud", "cad", "sgd", "aed", "chf", "jpy", "cny",
        "dollar", "dollars", "euro", "euros", "pound", "pounds", "dirham",
        "dirhams", "yen", "yuan", "rmb",
    }
)


#: Wrapping punctuation/space that may sit between a figure and the currency it
#: is quoted in (``40,000 (USD)``, ``(USD) 40,000``). Period words and sentence
#: punctuation are handled separately so a figure is never marked foreign by a
#: code in the next sentence.
_FOREIGN_WRAP = " \t\r\n()[]{}\"'"

#: Separators that may sit between a figure and the currency code/symbol quoted
#: with it (``40,000/month, USD``, ``40,000 - USD``, ``40,000/month/USD``).
#: Sentence punctuation is deliberately absent: a code in the next sentence is a
#: different figure's currency.
_FOREIGN_SEPARATORS = " \t\r\n/\\|,;:–—-()[]{}\"'~≈"

#: A bounded connector/preposition run that may sit between a figure's period
#: and the currency it is quoted in (``per month (in USD)``,
#: ``per month in US dollars``, ``per month (approx USD)``).
_FOREIGN_CONNECTORS = frozenset(
    {"in", "us", "approx", "approximately", "about", "around"}
)

#: A sentence terminator ends a figure's own sentence: a currency quoted in the
#: following sentence is not this figure's currency.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]\s|\n")


def _foreign_currency_before(text: str, start: int) -> bool:
    """True when a foreign symbol/code in the figure's sentence precedes it."""
    window = text[:start]
    boundary = None
    for boundary in _SENTENCE_BOUNDARY_RE.finditer(window):
        pass
    if boundary is not None:
        window = window[boundary.end():]
    window = window.rstrip(_FOREIGN_WRAP + ":,;")
    if window and window[-1] in _FOREIGN_SYMBOLS:
        return True
    return any(
        word.casefold() in _FOREIGN_CODES for word in re.findall(r"[A-Za-z]+", window)
    )


def _foreign_currency_after(after: str) -> bool:
    """True when a foreign symbol/code (past separators/connectors) follows the figure."""
    rest = after
    while rest:
        separator = re.match(rf"[{re.escape(_FOREIGN_SEPARATORS)}]+", rest)
        if separator is not None:
            rest = rest[separator.end():]
            continue
        connector = re.match(r"([A-Za-z]+)", rest)
        if connector is not None and connector.group(1).casefold() in _FOREIGN_CONNECTORS:
            rest = rest[connector.end():]
            continue
        break
    if not rest:
        return False
    if rest[0] in _FOREIGN_SYMBOLS:
        return True
    code = re.match(r"([A-Za-z]+)", rest)
    return code is not None and code.group(1).casefold() in _FOREIGN_CODES


def _foreign_currency_adjacent(text: str, start: int, end: int) -> bool:
    """True when the amount spanning ``[start, end)`` is quoted in a foreign currency."""
    if _foreign_currency_before(text, start):
        return True
    after = text[end:]
    period = _AFTER_PERIOD_RE.match(after)
    if period is not None:
        after = after[period.end():]
    return _foreign_currency_after(after)

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

#: A negated "unpaid"/"commission only" is not a statement that the role is
#: unpaid: "we do not offer unpaid internships", "not an unpaid one", "not a
#: commission-only role". Such a negation must not override a real figure.
_UNPAID_NEGATION_RE = re.compile(
    r"\b(?:not|never|no(?:\s+longer)?|isn'?t|aren'?t|wasn'?t|weren'?t"
    r"|don'?t|doesn'?t|didn'?t|won'?t|can'?t|cannot)\s+"
    r"(?:(?:offer|offering|provide|providing|hire|hiring|accept|accepting|allow|allowing)\s+)?"
    r"(?:an?\s+)?(?:unpaid|commission[\s-]?only)\b"
    r"|\b(?:unpaid|commission[\s-]?only)\b\s+(?:roles?|internships?|positions?|jobs?)?\s*"
    r"(?:are|is|will\s+be|would\s+be|was|were)?\s*not\s+"
    r"(?:offered|available|provided|accepted|hiring|hired)\b",
    re.IGNORECASE,
)


def _has_unpaid_signal(text: str) -> bool:
    """True when the text claims the role is unpaid, ignoring a negated mention."""
    if not _UNPAID_RE.search(text):
        return False
    return bool(_UNPAID_RE.search(_UNPAID_NEGATION_RE.sub(" ", text)))


_PERFORMANCE_QUALIFIER = (
    r"performance[\s-]?based"
    r"|based\s+on\s+performance"
    r"|\bperformance\s+stipend\b"
    r"|\bvariable\s+(?:stipend|pay|component)\b"
)
#: An upper-bound cap ("up to"/"upto"/"up-to"/"up – to"), accepted in any
#: spacing or hyphen/dash spelling. A cap is not a fixed figure.
_CAP_RE = re.compile(r"\bup[\s\-–—]*to\b", re.IGNORECASE)
#: Qualifiers that make the amount they attach to conditional. A bare
#: "incentives" mention is an add-on component, not a condition on the base, so
#: a fixed monthly figure stays fixed alongside it.
_CONDITIONAL_RE = re.compile(
    rf"{_PERFORMANCE_QUALIFIER}|{_CAP_RE.pattern}",
    re.IGNORECASE,
)

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
    r"|\binternet\b|\bcertificate\b"
    r"|\bctc\b|\bpackages?\b|\btotal\s+compensation\b|\bcost\s+to\s+company\b",
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


def _unstated() -> StipendInfo:
    return StipendInfo(state=UNSTATED)


def _unit_scale(unit: str | None) -> int:
    """The multiplier for a recognised shorthand unit (``k`` / lakh)."""
    return 1000 if unit and unit.casefold() == "k" else 100_000


def _to_int(number: str, unit: str | None, multiplier: int = 1) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except (TypeError, ValueError):
        return None
    value *= _unit_scale(unit) if unit else multiplier
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
    cap: bool = False
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
    return bool(_CONDITIONAL_RE.search(clause))


def _is_cap(clause: str) -> bool:
    return bool(_CAP_RE.search(clause))


def _is_nonbase(text: str, start: int, end: int, clause_left: int, clause_right: int) -> bool:
    # An extras noun (allowance/travel/internet/one-time/bonus...) marks the
    # amount only when it is directly adjacent to it: immediately before the
    # figure in its own label, or the noun immediately attached right after it
    # with no stated period in between. A cue in the clause never rescues an
    # adjacent extras noun, so "Travel stipend ₹2,000/month" is a travel amount,
    # not the stipend base. A benefit word that is merely elsewhere in the clause
    # is detached and leaves the stipend as the base. The preceding label stops
    # at the previous figure, so an earlier amount's extras noun ("Travel
    # allowance ₹2,000/month stipend ₹30,000/month") cannot poison the base.
    prefix = text[clause_left:start]
    label_start = 0
    for digit in re.finditer(r"\d", prefix):
        label_start = digit.end()
    if _NONBASE_RE.search(prefix[label_start:]):
        return True
    if _period_after(text, end) is not None:
        return False
    return bool(_NONBASE_RE.match(text[end:clause_right].lstrip()))


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


def _range_period_after(text: str, pos: int) -> str | None:
    """``_period_after`` at the far end of a range whose connector starts at ``pos``."""
    match = _RANGE_TAIL_RE.match(text, pos)
    if match is None:
        return None
    return _period_after(text, match.end())


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
    embedded_period: bool = False,
) -> None:
    if _overlaps(covered, match.start(), match.end()):
        return
    number = match.group(1)
    shorthand = match.group(2) if match.lastindex and match.lastindex >= 2 else None
    value = _to_int(number, shorthand, multiplier)
    if value is None:
        return
    start, end = match.start(1), match.end(1)
    if _foreign_currency_adjacent(text, start, end):
        return
    if _DURATION_AFTER_RE.match(text, end):
        return
    # A *bare* four-digit year near a stipend is not a stipend; an explicit
    # currency/period/prefixed amount is never discarded this way. Guard on the
    # parsed value, not the raw token, so a trailing comma ("2015,") is handled.
    if bare and not shorthand and re.fullmatch(r"(?:19|20)\d{2}", number.replace(",", "").strip()):
        return
    period = None
    if not embedded_period:
        period = _period_after(text, match.end())
        if period is None:
            period = _range_period_after(text, match.end())
        if period == "other":
            return
        if period == "year":
            kind = "year"
    # A bare number only counts when its own clause talks about stipends; a
    # number in a neighbouring clause (experience, headcount, a PIN code) is not
    # the stipend and must never drag the governing figure below the floor.
    clause_left, clause_right = _clause_span(text, start)
    clause = text[clause_left:clause_right]
    # Rupees are a property of the posting, not the clause: a figure in a
    # rupee-denominated posting is rupees even when the marker sits in another
    # clause ("CTC ₹6,00,000. Stipend: 15,000 per month."), while a figure
    # quoted in another currency is already rejected above. A posting with no
    # rupee marker at all states no rupee amount.
    if not _INR_RE.search(clause) and not _INR_RE.search(text):
        return
    if bare and not _CUE_RE.search(clause):
        return
    if not embedded_period and period is None and _PREPOSED_YEAR_RE.search(
        text[clause_left:start]
    ):
        kind = "year"
    # A lakh figure with no stated period ("₹4.8 Lakhs") is the annual package,
    # not a monthly stipend; a stated month period keeps it monthly.
    if not embedded_period and period is None and (shorthand or "").casefold() in _LAKH_UNITS:
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
            cap=_is_cap(clause),
            nonbase=_is_nonbase(text, start, end, clause_left, clause_right),
            divisor=divisor,
            cue_rank=_cue_rank(clause),
        )
    )
    covered.append((match.start(), match.end()))


def _is_full_number(number: str) -> bool:
    """A written-out amount ("25,000"), not the shorthand end of a K range ("25")."""
    if "," in number:
        return True
    try:
        return float(number) >= 1000
    except ValueError:
        return False


def _add_range(
    amounts: list[_Amount],
    covered: list[tuple[int, int]],
    text: str,
    match: re.Match,
    *,
    multiplier: int,
    kind: str,
    value_groups: tuple[int, int] = (1, 2),
    shorthand_groups: tuple[int | None, int | None] = (None, None),
) -> None:
    """Record both ends of a shorthand range whose unit applies to both numbers."""
    if _overlaps(covered, match.start(), match.end()):
        return
    period = _period_after(text, match.end())
    if period == "other":
        return
    if period == "year":
        kind = "year"
    if _foreign_currency_adjacent(text, match.start(), match.end()):
        return
    clause_left, clause_right = _clause_span(text, match.start(value_groups[0]))
    clause = text[clause_left:clause_right]
    # A rupee marker anywhere in the posting governs both ends, as it does for
    # a single amount.
    if not _INR_RE.search(clause) and not _INR_RE.search(text):
        return
    if period is None and _PREPOSED_YEAR_RE.search(text[clause_left:match.start(value_groups[0])]):
        kind = "year"
    for group_start, shorthand_group in zip(value_groups, shorthand_groups):
        number = match.group(group_start)
        shorthand = match.group(shorthand_group) if shorthand_group is not None else None
        # A shorthand end ("30" of "25,000-30k") takes the range's unit; a
        # written-out end keeps its own value and is never scaled by the other
        # end's K.
        scale = multiplier if shorthand or not _is_full_number(number) else 1
        value = _to_int(number, shorthand, scale)
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
                cap=_is_cap(clause),
                nonbase=_is_nonbase(text, start, end, clause_left, clause_right),
                cue_rank=_cue_rank(clause),
            )
        )
    covered.append((match.start(), match.end()))


def _collect_amounts(text: str) -> list[_Amount]:
    amounts: list[_Amount] = []
    covered: list[tuple[int, int]] = []
    for match in _RANGE_K_RE.finditer(text):
        _add_range(
            amounts,
            covered,
            text,
            match,
            multiplier=1000,
            kind="month",
            value_groups=(1, 3),
            shorthand_groups=(2, 4),
        )
    for match in _RANGE_LPA_RE.finditer(text):
        _add_range(amounts, covered, text, match, multiplier=100_000, kind="year")
    for match in _MONEY_MONTH_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", embedded_period=True)
    for match in _MONEY_YEAR_RE.finditer(text):
        _add(amounts, covered, text, match, kind="year", embedded_period=True)
    for match in _MONEY_LPA_RE.finditer(text):
        _add(
            amounts,
            covered,
            text,
            match,
            kind="year",
            multiplier=100_000,
            embedded_period=True,
        )
    for match in _MONEY_PREFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", lump_ok=True)
    for match in _MONEY_SUFFIX_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", lump_ok=True)
    # Bare numbers count only when they sit in stipend context and do not
    # overlap an amount already found by a currency/period pattern.
    for match in _BARE_AMOUNT_RE.finditer(text):
        _add(amounts, covered, text, match, kind="month", bare=True, lump_ok=True)
    return amounts


def _confirmed(text: str, governing: list[_Amount], floor: int) -> StipendInfo:
    """Classify the floor against the chosen governing stipend figures."""
    ordered = sorted(governing, key=lambda a: a.start)
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
    return StipendInfo(state=state, amount=low, amount_high=high)


def classify_stipend(
    text: str,
    *,
    floor: int = DEFAULT_FLOOR,
) -> StipendInfo:
    """Classify a posting's stipend text against a monthly floor.

    An amount is read only in a rupee posting (one carrying an INR marker); a
    figure quoted in another currency is never invented into rupees.
    """
    text = text or ""
    amounts = _collect_amounts(text)
    unpaid_signal = _has_unpaid_signal(text)

    # Judge the floor against the posting's governing stipend figure: the fixed
    # base amount carrying the strongest pay cue. A conditional or non-base
    # amount never outranks a fixed base, so an explicitly stated fixed monthly
    # figure stays confirmed even when a nearby "up to"/performance/incentive
    # mention shares the posting.
    base = [a for a in amounts if a.is_base]
    if base:
        base_rank = max(a.cue_rank for a in base)
        governing = [a for a in base if a.cue_rank == base_rank]
        if base_rank == 0:
            # A cue-less annual package yields to a cue-less monthly figure, so
            # "CTC ₹6,00,000/annum. ₹15,000/month" is judged on the monthly rate.
            monthly = [a for a in governing if a.kind == "month"]
            if monthly:
                governing = monthly
        # An explicit unpaid statement is overridden only by a figure tied to the
        # stipend itself (a stipend/remuneration cue), never by a broader salary
        # or package figure.
        if not (unpaid_signal and base_rank < 2):
            return _confirmed(text, governing, floor)

    if unpaid_signal:
        return StipendInfo(state=UNPAID)

    # With no fixed base, an "up to" cap is not a figure that can confirm the
    # floor. A cap that is itself below the floor still identifies a below-floor
    # stipend; a cap at or above the floor is unknown, never confirmed.
    caps = [a for a in amounts if a.cap and not a.nonbase]
    if caps:
        cap_rank = max(a.cue_rank for a in caps)
        info = _confirmed(text, [a for a in caps if a.cue_rank == cap_rank], floor)
        if info.state == CONFIRMED_BELOW_FLOOR:
            return info
    return _unstated()
