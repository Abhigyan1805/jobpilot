"""Interpret when a posting plausibly runs.

The captain needs an internship in a January-to-May/June window. Postings rarely
state exact dates, so this module extracts whatever timing signal exists and
returns a bounded judgement:

* explicit month ranges are authoritative (confidence 1.0);
* season words ("Summer 2026") are a strong signal (confidence 0.6);
* no timing signal is "unknown" (confidence 0.0) and config decides whether
  unknown-window internships are allowed through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2, "feburary": 2,
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
MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

RANGE_RE = re.compile(
    rf"\b(?P<m1>{MONTH_ALT})\.?(?:\s*(?P<y1>(?:19|20)\d{{2}}))?\s*"
    rf"(?:-|–|—|to|through|until|till)\s*"
    rf"(?P<m2>{MONTH_ALT})\.?(?:\s*(?P<y2>(?:19|20)\d{{2}}))?\b",
    re.IGNORECASE,
)
SINGLE_RE = re.compile(rf"\b(?P<m1>{MONTH_ALT})\.?\s+(?P<y1>(?:19|20)\d{{2}})\b", re.IGNORECASE)
SEASON_RE = re.compile(r"\b(?P<season>spring|summer|autumn|fall|winter|monsoon)\b", re.IGNORECASE)

SEASON_MONTHS = {
    "spring": {1, 2, 3, 4, 5},
    "summer": {5, 6, 7, 8},
    "autumn": {9, 10, 11},
    "fall": {9, 10, 11},
    "winter": {12, 1, 2},
    "monsoon": {6, 7, 8, 9},
}
NUMERIC_RANGE_RE = re.compile(
    r"\b(?P<m1>0?[1-9]|1[0-2])\s*/\s*(?P<y1>\d{4})?\s*(?:-|–|—|to)\s*(?P<m2>0?[1-9]|1[0-2])\s*/\s*(?P<y2>\d{4})\b"
)
# ISO date ranges such as "2026-01-15 - 2026-06-30", used by sources (Unstop)
# that expose a typed start/end date pair. Only a genuine pair is meaningful: a
# lone ISO date is deliberately not treated as a timing signal, because a posted
# or deadline date would otherwise hard-reject an in-window internship.
ISO_RANGE_RE = re.compile(
    r"\b(?P<y1>(?:19|20)\d{2})-(?P<m1>0[1-9]|1[0-2])-\d{2}"
    r"\s*(?:-|–|—|to|through|until|till)\s*"
    r"(?P<y2>(?:19|20)\d{2})-(?P<m2>0[1-9]|1[0-2])-\d{2}\b",
    re.IGNORECASE,
)
YEAR_TOKEN_RE = re.compile(r"^(?:19|20)\d{2}$")
# Season words only count when they sit next to internship/term context (or a
# year) so that product/technology names such as "Spring Boot" cannot corrupt
# the window judgement.
SEASON_CONTEXT = {
    "intern", "interns", "internship", "internships", "coop", "co-op",
    "cooperative", "trainee", "term", "analyst", "placement", "program",
    "programme", "session", "semester",
}
# "Spring" is also a technology name; when it heads one of these products it is
# not a timing signal.
SPRING_TECH_SUFFIXES = {
    "boot", "cloud", "framework", "security", "mvc", "batch", "webflux",
    "jpa", "graphql", "actuator", "data",
}
# Words that name a timing window. An ISO date pair only counts when one of
# these sits next to it *in the description itself*; a bare "Internship" token
# leaked in from a concatenated field is not a timing word.
WINDOW_CONTEXT = {
    "start", "starts", "starting", "begin", "begins", "beginning",
    "commence", "commences", "commencing", "duration", "week", "weeks",
    "month", "months", "term", "terms", "semester", "semesters",
    "summer", "winter", "spring", "autumn", "fall", "monsoon",
    "window", "period", "placement", *MONTHS,
}
# Explicit deadline/application phrases veto an ISO pair: an application range
# or deadline is not the internship's window even when timing words appear
# nearby. The phrase must sit in the pair's own clause, so deadline prose in a
# following sentence cannot demote a genuine typed window.
DEADLINE_PHRASES = (
    "apply by",
    "application window",
    "applications close",
    "application closes",
    "applications accepted",
    "application accepted",
    "applications are invited",
    "deadline",
)
# Clause terminators bound how far a deadline phrase or timing word reaches
# around a date pair.
_CLAUSE_BREAKS = ".!?\n;"


def _season_has_context(text: str, match: re.Match, season: str) -> bool:
    before = re.findall(r"[A-Za-z0-9-]+", text[: match.start()])[-2:]
    after = re.findall(r"[A-Za-z0-9-]+", text[match.end():])[:2]
    if season == "spring" and after and after[0].lower() in SPRING_TECH_SUFFIXES:
        return False
    for token in (*before, *after):
        lowered = token.lower()
        if lowered in SEASON_CONTEXT or YEAR_TOKEN_RE.match(lowered):
            return True
    return False


def _clause_before(text: str, pos: int) -> str:
    cut = max(text.rfind(ch, 0, pos) for ch in _CLAUSE_BREAKS)
    return text[cut + 1: pos]


def _clause_after(text: str, pos: int) -> str:
    stops = [text.find(ch, pos) for ch in _CLAUSE_BREAKS]
    stops = [stop for stop in stops if stop != -1]
    return text[pos: min(stops)] if stops else text[pos:]


def _range_has_context(text: str, match: re.Match) -> bool:
    """Whether an ISO date pair is the posting's own window.

    Only a genuine timing word in the pair's own clause establishes a window,
    and an explicit deadline/application phrase in that same clause vetoes it,
    because an application or deadline range is not the internship's window.
    ``text`` is the posting's own prose (the description), so an adjacent
    concatenated field such as ``employment_type`` can never supply the context.
    """
    before = _clause_before(text, match.start())
    after = _clause_after(text, match.end())
    label = f"{before} {after}".lower()
    if any(re.search(rf"\b{re.escape(phrase)}\b", label) for phrase in DEADLINE_PHRASES):
        return False
    nearby = [
        token.lower()
        for token in (*re.findall(r"[A-Za-z0-9-]+", before)[-2:], *re.findall(r"[A-Za-z0-9-]+", after)[:2])
    ]
    return any(token in WINDOW_CONTEXT for token in nearby)


@dataclass
class WindowInfo:
    label: str
    confidence: float
    overlaps: bool | None
    detail: str = ""

    def to_dict(self) -> dict:
        return {"label": self.label, "confidence": self.confidence, "overlaps": self.overlaps, "detail": self.detail}


def _window_months(cfg) -> set[int]:
    return set(range(int(cfg.window_start_month), int(cfg.window_end_month) + 1))


def _label(start: int, end: int, year: str = "") -> str:
    def name(m: int) -> str:
        for k, v in MONTHS.items():
            if v == m and len(k) > 3:
                return k[:3].capitalize()
        return str(m)

    return f"{name(start)}-{name(end)}{(' ' + year) if year else ''}"


def classify_window(text: str, cfg, *, prose: str | None = None) -> WindowInfo:
    """Classify a posting's timing.

    ``text`` is the searchable text scanned for every signal. ``prose`` is the
    posting's own description, used for ISO date pairs so that context cannot
    leak in from a concatenated field such as the employment type; when omitted
    (direct callers with a plain string) ``text`` stands in for it.
    """
    if not text:
        return WindowInfo("unknown", 0.0, None, "no text to inspect")
    window = _window_months(cfg)
    iso_text = text if prose is None else prose

    # 1. Explicit month-name ranges (highest confidence).
    for m in RANGE_RE.finditer(text):
        m1 = MONTHS.get(m.group("m1").lower())
        m2 = MONTHS.get(m.group("m2").lower())
        if not m1 or not m2:
            continue
        if m2 >= m1:
            months = set(range(m1, m2 + 1))
        else:
            months = set(range(m1, 13)) | set(range(1, m2 + 1))
        label = _label(m1, m2, m.group("y1") or m.group("y2") or "")
        overlap = bool(months & window)
        return WindowInfo(label, 1.0, overlap, f"explicit range {label}")

    # 2. ISO date ranges (e.g. Unstop's typed start_date - end_date). Only a
    #    pair next to genuine timing words in the description itself counts as
    #    the posting's window: a bare date pair in prose is an application or
    #    deadline range, so reading it as the window would wrongly reject (or
    #    wrongly verify) a posting.
    for m in ISO_RANGE_RE.finditer(iso_text):
        if not _range_has_context(iso_text, m):
            continue
        m1, m2 = int(m.group("m1")), int(m.group("m2"))
        if m2 >= m1:
            months = set(range(m1, m2 + 1))
        else:
            months = set(range(m1, 13)) | set(range(1, m2 + 1))
        label = _label(m1, m2, m.group("y1") or m.group("y2") or "")
        return WindowInfo(label, 1.0, bool(months & window), f"explicit range {label}")

    # 3. Numeric month/year ranges such as 01/2026 - 06/2026.
    for m in NUMERIC_RANGE_RE.finditer(text):
        m1, m2 = int(m.group("m1")), int(m.group("m2"))
        months = set(range(min(m1, m2), max(m1, m2) + 1))
        label = _label(min(m1, m2), max(m1, m2), m.group("y1") or m.group("y2") or "")
        return WindowInfo(label, 1.0, bool(months & window), f"explicit range {label}")

    # 4. Season words, but only when a nearby internship/term word or year
    #    confirms the season is really the posting's timing and not a tech name.
    for m in SEASON_RE.finditer(text):
        season = m.group("season").lower()
        if not _season_has_context(text, m, season):
            continue
        months = SEASON_MONTHS[season]
        year = ""
        tail = text[m.end(): m.end() + 12]
        ym = re.search(r"((?:19|20)\d{2})", tail)
        if ym:
            year = ym.group(1)
        label = f"{season.capitalize()}{(' ' + year) if year else ''}"
        return WindowInfo(label, 0.6, bool(months & window), f"season {label}")

    # 5. A single month-year is weak but usable.
    singles = list(SINGLE_RE.finditer(text))
    if singles:
        for m in singles:
            mon = MONTHS.get(m.group("m1").lower())
            if mon:
                label = _label(mon, mon, m.group("y1"))
                return WindowInfo(label, 0.4, mon in window, f"single month {label}")

    return WindowInfo("unknown", 0.0, None, "no timing signal found")
