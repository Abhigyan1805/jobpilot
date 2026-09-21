"""Local JSON postings adapter.

Reads an array (or {"jobs": [...]}) of posting objects from a file. Useful for
offline verification, fixtures and the dry-run walkthrough, and a demonstration
that discovery sources are genuinely pluggable behind one interface.
"""

from __future__ import annotations

import json
from pathlib import Path

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError
from jobpilot.models import JobPosting


class LocalFileAdapter(SourceAdapter):
    name = "local"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        raw_path = self.option("path", "")
        if not raw_path:
            raise FetchError("sources.local.path is not set")
        path = Path(self.config.resolve(str(raw_path)))
        if not path.exists():
            raise FetchError(f"local postings file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        postings: list[JobPosting] = []
        for i, job in enumerate(jobs):
            desc = job.get("description", "") or ""
            if "<" in desc:
                desc = html_to_text(desc)
            postings.append(
                JobPosting(
                    source=self.name,
                    job_id=str(job.get("id") or job.get("job_id") or i),
                    company=job.get("company", ""),
                    title=job.get("title", ""),
                    url=job.get("url", ""),
                    apply_url=job.get("apply_url", job.get("url", "")),
                    location=job.get("location", ""),
                    description=desc,
                    employment_type=job.get("employment_type", ""),
                    published_at=job.get("published_at", ""),
                    is_remote=job.get("is_remote"),
                    raw=job,
                )
            )
        return postings
