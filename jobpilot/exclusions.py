"""A configurable exclusion list of postings already applied to.

After working through every posting on the review page the captain does not want
to see those again. This is deliberately a *filter*, never a deletion: the
postings stay in the store and the review queue, and ``jobpilot present`` simply
drops any posting the exclusion list matches before it renders.

Entries are matched by *identity only*, the way a re-discovery of the exact same
posting would be, so the list keeps working across runs without hiding a
genuinely new posting that shares a company and a generic title:

* on ``url`` (scheme/host/case/trailing-slash normalised; the query string is
  kept, with its parameters order-normalised, because some boards carry the job
  identity in the query and dropping it would hide a genuinely new posting), and
* exactly on a supplied ``stable_id`` or ``source`` + ``job_id``.

An entry with neither a url nor a source/job id matches nothing; there is no
company+title fallback.

The list lives in a tracked TOML data file (``data/applied-postings.toml`` by
default) referenced from ``[filter].exclude_file``. A missing or empty file
means no exclusions.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _norm_url(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        host = parts.netloc.casefold()
        path = parts.path.rstrip("/").casefold()
        query = "&".join(sorted(parts.query.split("&"))) if parts.query else ""
        return urlunsplit((parts.scheme.casefold(), host, path, query, ""))
    return text.rstrip("/").casefold()


@dataclass(frozen=True)
class ExclusionEntry:
    source: str = ""
    company: str = ""
    title: str = ""
    url: str = ""
    stable_id: str = ""
    job_id: str = ""

    def label(self) -> str:
        if self.company and self.title:
            return f"{self.company} - {self.title}"
        return self.url or self.stable_id or self.job_id or "excluded posting"


@dataclass
class ExclusionList:
    entries: tuple[ExclusionEntry, ...] = ()

    @property
    def count(self) -> int:
        return len(self.entries)

    @classmethod
    def load(cls, path: str | Path | None) -> ExclusionList:
        """Load entries from a TOML file; a missing/blank path yields an empty list."""
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        with p.open("rb") as fh:
            raw = tomllib.load(fh)
        if not isinstance(raw, dict):
            return cls()
        rows = raw.get("applied") or raw.get("exclusions") or []
        known = {f.name for f in fields(ExclusionEntry)}
        entries: list[ExclusionEntry] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, str):
                    entries.append(ExclusionEntry(url=row))
                elif isinstance(row, dict):
                    entries.append(
                        ExclusionEntry(**{k: str(v) for k, v in row.items() if k in known})
                    )
        return cls(entries=tuple(entries))

    def match(self, posting) -> ExclusionEntry | None:
        """Return the entry matching the posting's identity, or ``None``."""
        url = _norm_url(getattr(posting, "url", ""))
        apply_url = _norm_url(getattr(posting, "apply_url", ""))
        source = str(getattr(posting, "source", ""))
        job_id = str(getattr(posting, "job_id", ""))
        stable_id = f"{source}:{job_id}" if source else job_id

        for entry in self.entries:
            if entry.stable_id and entry.stable_id == stable_id:
                return entry
            if entry.source and entry.job_id and entry.source == source and entry.job_id == job_id:
                return entry
            entry_url = _norm_url(entry.url)
            if entry_url and (entry_url == url or entry_url == apply_url):
                return entry
        return None
