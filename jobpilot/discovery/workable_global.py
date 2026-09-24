"""Workable global job-search adapter (no authentication).

Endpoint verified live:

    GET https://jobs.workable.com/api/v1/jobs?query=intern&location=India

This is Workable's cross-company search (distinct from the per-account widget
in :mod:`jobpilot.discovery.workable`). It returns real India internships in
structured JSON and paginates with an opaque ``pageToken`` parameter.

Honest limitations: the endpoint is **undocumented**, so it may change and is
kept behind the same "one source failing never aborts the run" contract.
``jobs.workable.com/robots.txt`` sets ``Content-Signal: ai-train=no`` (so its
data must not be used for model training) and disallows ``/search`` but not
``/api/v1/jobs``. Its ``employmentType`` field is unreliable - live intern rows
were tagged ``Full-time``/``Other``/empty - so this adapter relies on Workable's
own server-side ``query=intern`` search rather than re-checking the typed field.
"""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://jobs.workable.com/api/v1/jobs"


class WorkableGlobalAdapter(SourceAdapter):
    name = "workable_global"
    requires_tokens = False
    hosts = ("jobs.workable.com",)

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        max_pages = int(self.option("max_pages", 2))
        query = str(self.option("query", "intern"))
        location = str(self.option("location", "India"))
        token = ""
        for _page in range(1, max_pages + 1):
            params = {"query": query, "location": location}
            if token:
                params["pageToken"] = token
            url = f"{SEARCH_URL}?{urlencode(params)}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
            except FetchError as exc:
                errors.append(str(exc))
                break
            jobs = data.get("jobs") or [] if isinstance(data, dict) else []
            if not jobs:
                break
            for job in jobs:
                postings.append(self._normalise(job))
            token = str(data.get("nextPageToken") or "")
            if not token:
                break

        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, job: dict) -> JobPosting:
        company = job.get("company") or {}
        company_title = company.get("title") if isinstance(company, dict) else str(company or "")

        location = job.get("location") or {}
        if isinstance(location, dict):
            location_text = ", ".join(
                str(p)
                for p in [location.get("city"), location.get("subregion"), location.get("countryName")]
                if p
            )
        else:
            location_text = str(location or "")

        workplace = str(job.get("workplace") or "").lower()
        is_remote = True if workplace == "remote" else None

        return JobPosting(
            source=self.name,
            job_id=str(job.get("id") or job.get("url") or job.get("title") or ""),
            company=company_title or "",
            title=job.get("title") or "",
            url=job.get("url") or "",
            apply_url=job.get("url") or "",
            location=location_text,
            description=html_to_text(job.get("description") or ""),
            employment_type=job.get("employmentType") or "",
            published_at=str(job.get("created") or job.get("updated") or ""),
            is_remote=is_remote,
            raw=job,
        )
