"""Workable public widget adapter (no authentication)."""

from __future__ import annotations

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

BOARD_URL = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


class WorkableAdapter(SourceAdapter):
    name = "workable"
    hosts = ("apply.workable.com",)

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        for token in self.tokens:
            url = BOARD_URL.format(token=token)
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)))
            except FetchError as exc:
                errors.append(f"{token}: {exc}")
                continue
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            for job in jobs:
                postings.append(self._normalise(token, data.get("name") or token, job))
        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, token: str, company: str, job: dict) -> JobPosting:
        locations = job.get("locations") or []
        loc_bits = []
        for loc in locations:
            if isinstance(loc, dict):
                part = ", ".join(p for p in [loc.get("city"), loc.get("region"), loc.get("country")] if p)
                if part:
                    loc_bits.append(part)
        primary = ", ".join(p for p in [job.get("city"), job.get("state"), job.get("country")] if p)
        location = " | ".join(dict.fromkeys([p for p in [primary, *loc_bits] if p]))
        remote = job.get("telecommuting")
        return JobPosting(
            source=self.name,
            job_id=str(job.get("shortcode") or job.get("id")),
            company=company,
            title=job.get("title", "") or "",
            url=job.get("url", "") or "",
            apply_url=job.get("application_url", "") or job.get("url", "") or "",
            location=location,
            description=html_to_text(job.get("description", "")),
            employment_type=job.get("employment_type", "") or "",
            published_at=str(job.get("published_on") or job.get("created_at") or ""),
            is_remote=bool(remote) if remote is not None else None,
            raw=job,
        )
