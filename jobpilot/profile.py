"""Parse the master profile markdown into structured, citable content.

The profile is the only source of resume facts. Every bullet and skill parsed
here keeps its original wording so that tailoring can only select, reorder and
re-emphasise - never rewrite a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

H2_RE = re.compile(r"^##\s+(.*)$")
H3_RE = re.compile(r"^###\s+(.*)$")
BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
ITALIC_RE = re.compile(r"^\*(.+)\*$")
SKILL_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
CONTACT_RE = re.compile(r"^-\s+\*\*(.+?):\*\*\s*(.*)$")
MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
DATE_RANGE_RE = re.compile(
    rf"({MONTHS})\.?\s+\d{{4}}\s*[-–—to]+\s*(?:({MONTHS})\.?\s+\d{{4}}|present|current|now)",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
EMDASH = "\u2014"

_LOCATION_TAIL_RE = re.compile(
    r"(india|usa|united states|uk|united kingdom|remote|singapore|germany|canada|australia|netherlands)$",
    re.IGNORECASE,
)


def _looks_like_location(text: str) -> bool:
    return bool(_LOCATION_TAIL_RE.search(text.strip()))


@dataclass
class Entry:
    section: str
    title: str = ""
    org: str = ""
    location: str = ""
    dates: str = ""
    tagline: str = ""
    stack: str = ""
    note: str = ""
    bullets: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    year: str = ""
    tags: list[str] = field(default_factory=list)
    raw_heading: str = ""

    def searchable_text(self) -> str:
        return " ".join(
            p
            for p in [self.title, self.org, self.location, self.tagline, self.stack, self.note, *self.bullets]
            if p
        )


@dataclass
class Profile:
    name: str = ""
    contact: dict[str, str] = field(default_factory=dict)
    education: list[Entry] = field(default_factory=list)
    experiences: list[Entry] = field(default_factory=list)
    projects: list[Entry] = field(default_factory=list)
    positions: list[Entry] = field(default_factory=list)
    skills: dict[str, list[str]] = field(default_factory=dict)
    raw_text: str = ""

    @property
    def all_bullets(self) -> list[str]:
        out: list[str] = []
        for group in (self.education, self.experiences, self.projects, self.positions):
            for entry in group:
                out.extend(entry.bullets)
        return out

    @property
    def all_entries(self) -> list[Entry]:
        return [*self.education, *self.experiences, *self.projects, *self.positions]

    def skill_terms(self) -> list[str]:
        out: list[str] = []
        for items in self.skills.values():
            out.extend(items)
        return out


def _split_heading(heading: str) -> list[str]:
    parts = [p.strip() for p in re.split(rf"\s*{EMDASH}\s*|\s+-\s+", heading) if p.strip()]
    return parts


def _extract_dates(text: str) -> str:
    m = DATE_RANGE_RE.search(text)
    if m:
        return m.group(0).strip()
    return ""


def _strip_dates(text: str) -> str:
    return DATE_RANGE_RE.sub("", text).strip(" \u2014-,")


def _parse_entry_heading(section: str, heading: str) -> Entry:
    entry = Entry(section=section, raw_heading=heading)
    parts = _split_heading(heading)

    # Pull a trailing year tag such as "(2026)" for projects.
    year_match = re.search(r"\((\d{4})\)\s*$", heading)
    if year_match:
        entry.year = year_match.group(1)
        heading = heading[: year_match.start()].strip()
        parts = _split_heading(heading)

    if section == "projects":
        entry.title = parts[0] if parts else heading
        if len(parts) > 1:
            entry.tagline = " ".join(parts[1:])
        return entry

    if section == "positions":
        entry.title = parts[0] if parts else heading
        rest = parts[1:]
        # Last part holding a date range is the dates; a middle part is the org.
        if rest and _extract_dates(rest[-1]):
            entry.dates = _extract_dates(rest[-1])
            rest = rest[:-1]
        if rest:
            entry.org = rest[0]
        return entry

    # experience / education
    entry.title = parts[0] if parts else heading
    rest = parts[1:]
    if rest and _extract_dates(rest[-1]):
        entry.dates = _extract_dates(rest[-1])
        rest = rest[:-1]
    if rest:
        org_loc = rest[0]
        loc_match = re.search(r"\((.*?)\)\s*$", org_loc)
        if loc_match:
            entry.location = loc_match.group(1).strip()
            org_loc = org_loc[: loc_match.start()].strip()
        else:
            # "Org, City, Country" -> split the trailing location off the org.
            loc_tail = re.match(r"^(.*?),\s*([^,]+,\s*[A-Za-z ]+)$", org_loc)
            if loc_tail and _looks_like_location(loc_tail.group(2)):
                org_loc = loc_tail.group(1).strip()
                entry.location = loc_tail.group(2).strip()
        entry.org = org_loc
    if len(rest) > 1:
        entry.location = entry.location or rest[1]
    return entry


def parse_profile_text(text: str) -> Profile:
    profile = Profile(raw_text=text)
    section = ""
    current: Entry | None = None

    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        h2 = H2_RE.match(stripped)
        if h2:
            section = h2.group(1).strip().lower()
            current = None
            continue
        h3 = H3_RE.match(stripped)
        if h3:
            heading = h3.group(1).strip()
            current = _parse_entry_heading(_canonical_section(section), heading)
            _append_entry(profile, current)
            continue
        if not stripped or re.fullmatch(r"[-*_]{3,}", stripped):
            continue

        # Title / contact block before the first H2.
        if section == "":
            if stripped.startswith("# "):
                name = stripped[2:].strip()
                profile.name = re.split(rf"\s*{EMDASH}\s*", name)[0].strip()
            cm = CONTACT_RE.match(stripped)
            if cm:
                profile.contact[cm.group(1).strip().lower()] = cm.group(2).strip()
            continue

        if section.startswith("education"):
            if stripped.startswith("**"):
                # The education block is plain bold text, not an H3 heading.
                plain = _clean_inline(stripped)
                plain = re.sub(r"^[-*]\s+", "", plain)
                dates = _extract_dates(plain)
                without_dates = _strip_dates(plain) if dates else plain
                parts = _split_heading(without_dates)
                entry = Entry(section="education", raw_heading=stripped)
                entry.title = parts[0] if parts else without_dates
                entry.org = entry.title
                if len(parts) > 1:
                    entry.location = parts[1]
                entry.dates = dates
                entry.note = without_dates
                profile.education.append(entry)
                current = entry
            elif current is not None:
                plain = _clean_inline(stripped)
                plain = re.sub(r"^[-*]\s+", "", plain)
                dates = _extract_dates(plain)
                if dates and not current.dates:
                    current.dates = dates
                degree = _strip_dates(plain) if dates else plain
                if degree:
                    current.tagline = (current.tagline + " " + degree).strip()
            continue

        if section.startswith("technical skills") or section.startswith("skills"):
            skill_line = re.sub(r"^[-*]\s+", "", stripped)
            sm = SKILL_RE.match(skill_line)
            if sm:
                category = sm.group(1).strip()
                items = [i.strip() for i in re.split(r",|;", sm.group(2)) if i.strip()]
                profile.skills.setdefault(category, [])
                for item in items:
                    if item not in profile.skills[category]:
                        profile.skills[category].append(item)
            continue

        if current is not None:
            italic = ITALIC_RE.match(stripped)
            bullet = BULLET_RE.match(stripped)
            if bullet:
                body = bullet.group(1).strip()
                body = _clean_inline(body)
                if re.match(r"(?i)^repo:", body) or body.startswith("http") or "github.com" in body:
                    current.links.append(body)
                else:
                    current.bullets.append(body)
            elif italic:
                note = italic.group(1).strip()
                if note.startswith("non-ai") or note.startswith("non-ai/ml") or "excluded" in note.lower():
                    current.tags.append("non_ai")
                elif current.section == "projects" and not current.stack:
                    current.stack = note
                else:
                    current.note = (current.note + " " + note).strip()
            else:
                current.note = (current.note + " " + _clean_inline(stripped)).strip()
    return profile


def _clean_inline(text: str) -> str:
    # Remove markdown emphasis/bold markers but keep the words and numbers.
    text = text.replace("**", "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def _canonical_section(section: str) -> str:
    if section.startswith("education"):
        return "education"
    if section.startswith("experience"):
        return "experience"
    if section.startswith("project"):
        return "projects"
    if section.startswith("position"):
        return "positions"
    return section


def _append_entry(profile: Profile, entry: Entry) -> None:
    if entry.section == "education":
        profile.education.append(entry)
    elif entry.section == "experience":
        profile.experiences.append(entry)
    elif entry.section == "projects":
        profile.projects.append(entry)
    elif entry.section == "positions":
        profile.positions.append(entry)


def load_profile(path: str | Path) -> Profile:
    text = Path(path).read_text(encoding="utf-8")
    return parse_profile_text(text)
