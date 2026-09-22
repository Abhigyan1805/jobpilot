"""Himalayas public job-search adapter (no authentication).

Endpoint verified live on 2026-09-21/22:

    GET https://himalayas.app/jobs/api/search?employment_type=Intern&country=India

Returns ``{jobs: [...], totalCount, page, limit}`` and paginates with an integer
``page`` parameter (20 per page). The API is free and needs no key. Himalayas'
terms require a visible link back to himalayas.app and the attribution "data
sourced from Himalayas"; they also forbid republishing its jobs to
LinkedIn/Google Jobs/Jooble/Neuvoo. This adapter only reads the feed and records
the attribution in each posting's raw payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://himalayas.app/jobs/api/search"
PAGE_SIZE = 20


def _iso(timestamp) -> str:
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(timestamp or "")


class HimalayasAdapter(SourceAdapter):
    name = "himalayas"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        max_pages = int(self.option("max_pages", 1))
        queries = self.option("queries")
        if queries is None:
            single = self.option("query")
            queries = [single] if single else [None]

        base = {
            "employment_type": str(self.option("employment_type", "Intern")),
            "country": str(self.option("country", "India")),
        }
        if self.option("worldwide"):
            base["worldwide"] = "true"

        for query in queries:
            for page in range(1, max_pages + 1):
                params = dict(base)
                params["page"] = page
                if query:
                    params["q"] = str(query)
                url = f"{SEARCH_URL}?{urlencode(params)}"
                try:
                    data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
                except FetchError as exc:
                    errors.append(f"{query or 'all'}: {exc}")
                    break
                jobs = data.get("jobs") or [] if isinstance(data, dict) else []
                if not jobs:
                    break
                for job in jobs:
                    postings.append(self._normalise(job))
                total = data.get("totalCount")
                if len(jobs) < PAGE_SIZE:
                    break
                if total is not None and page * PAGE_SIZE >= int(total):
                    break

        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, job: dict) -> JobPosting:
        restrictions = [str(x) for x in (job.get("locationRestrictions") or []) if x]
        if restrictions:
            location = ", ".join(restrictions)
            is_remote = "worldwide" in location.lower() or None
        else:
            location = "Worldwide"
            is_remote = True

        description = job.get("description") or ""
        text = html_to_text(description) if description else ""
        excerpt = job.get("excerpt") or ""
        if excerpt and excerpt not in text:
            text = f"{text}\n{excerpt}".strip()

        link = job.get("applicationLink") or ""
        return JobPosting(
            source=self.name,
            job_id=str(job.get("guid") or link or job.get("title") or ""),
            company=job.get("companyName") or "",
            title=job.get("title") or "",
            url=link,
            apply_url=link,
            location=location,
            description=text,
            employment_type=job.get("employmentType") or "",
            published_at=_iso(job.get("pubDate")),
            is_remote=is_remote,
            salary=self._salary(job),
            raw=job,
        )

    @staticmethod
    def _salary(job: dict) -> str:
        low, high = job.get("minSalary"), job.get("maxSalary")
        period = job.get("salaryPeriod") or ""
        currency = job.get("currency") or ""
        if low is None and high is None:
            return ""
        span = f"{low or ''}-{high or ''}".strip("-")
        return " ".join(p for p in [span, currency, period] if p)
