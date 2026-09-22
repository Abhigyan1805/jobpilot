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


def classify_window(text: str, cfg) -> WindowInfo:
    if not text:
        return WindowInfo("unknown", 0.0, None, "no text to inspect")
    window = _window_months(cfg)

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

    # 2. Numeric month/year ranges such as 01/2026 - 06/2026.
    for m in NUMERIC_RANGE_RE.finditer(text):
        m1, m2 = int(m.group("m1")), int(m.group("m2"))
        months = set(range(min(m1, m2), max(m1, m2) + 1))
        label = _label(min(m1, m2), max(m1, m2), m.group("y1") or m.group("y2") or "")
        return WindowInfo(label, 1.0, bool(months & window), f"explicit range {label}")

    # 3. Season words, but only when a nearby internship/term word or year
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

    # 4. A single month-year is weak but usable.
    singles = list(SINGLE_RE.finditer(text))
    if singles:
        for m in singles:
            mon = MONTHS.get(m.group("m1").lower())
            if mon:
                label = _label(mon, mon, m.group("y1"))
                return WindowInfo(label, 0.4, mon in window, f"single month {label}")

    return WindowInfo("unknown", 0.0, None, "no timing signal found")
