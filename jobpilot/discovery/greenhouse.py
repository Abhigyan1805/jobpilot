"""Greenhouse public job-board adapter (no authentication)."""

from __future__ import annotations

import html as _html

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"
    hosts = ("boards-api.greenhouse.io",)

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
            for job in data.get("jobs", []) or []:
                postings.append(self._normalise(token, job))
        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, token: str, job: dict) -> JobPosting:
        location = (job.get("location") or {}).get("name", "") if isinstance(job.get("location"), dict) else ""
        content = _html.unescape(job.get("content", "") or "")
        description = html_to_text(content)
        employment_type = self._employment_type(job)
        return JobPosting(
            source=self.name,
            job_id=str(job.get("id")),
            company=job.get("company_name") or token,
            title=job.get("title", "") or "",
            url=job.get("absolute_url", "") or "",
            apply_url=job.get("absolute_url", "") or "",
            location=location,
            description=description,
            employment_type=employment_type,
            published_at=job.get("first_published") or job.get("updated_at") or "",
            is_remote=("remote" in location.lower()) or None,
            raw=job,
        )

    @staticmethod
    def _employment_type(job: dict) -> str:
        for meta in job.get("metadata", []) or []:
            name = str(meta.get("name", "")).lower()
            if "employment" in name or "commitment" in name or "type" in name:
                value = meta.get("value")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
