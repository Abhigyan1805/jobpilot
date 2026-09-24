"""Ashby public job-board adapter (no authentication)."""

from __future__ import annotations

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


class AshbyAdapter(SourceAdapter):
    name = "ashby"

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
                if job.get("isListed") is False:
                    continue
                postings.append(self._normalise(token, job))
        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, token: str, job: dict) -> JobPosting:
        location = job.get("location", "") or ""
        secondary = job.get("secondaryLocations") or []
        location_all = ", ".join(
            [loc for loc in [location, *[s.get("location", "") if isinstance(s, dict) else str(s) for s in secondary]] if loc]
        )
        address = job.get("address") or {}
        remote = job.get("isRemote")
        if remote is None:
            remote = ("remote" in location_all.lower()) or None
        return JobPosting(
            source=self.name,
            job_id=str(job.get("id")),
            company=token,
            title=job.get("title", "") or "",
            url=job.get("jobUrl", "") or "",
            apply_url=job.get("applyUrl", "") or job.get("jobUrl", "") or "",
            location=location_all,
            description=html_to_text(job.get("descriptionHtml", "")),
            employment_type=job.get("employmentType", "") or "",
            published_at=str(job.get("publishedAt", "") or ""),
            is_remote=bool(remote) if remote is not None else None,
            salary=job.get("compensation", {}).get("compensationTierSummary", "")
            if isinstance(job.get("compensation"), dict)
            else "",
            raw={**job, "_address": address},
        )
