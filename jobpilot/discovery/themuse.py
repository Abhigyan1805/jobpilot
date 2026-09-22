"""The Muse public jobs adapter (no authentication).

Endpoint verified live:

    GET https://www.themuse.com/api/public/jobs?page=N&level=Internship&location=India

Returns ``{page, page_count, items_per_page, total, results}`` (20 per page).
The API is public and free (500 requests/hour unauthenticated, 3,600 with a
registered key). ``level=Internship`` is a typed filter. ``location=India`` is
loose - the report observed a US role in the India results - so the shared hard
location filter validates each hit rather than trusting the parameter.
"""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://www.themuse.com/api/public/jobs"
PAGE_SIZE = 20


class TheMuseAdapter(SourceAdapter):
    name = "themuse"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        max_pages = int(self.option("max_pages", 2))
        params = {"level": str(self.option("level", "Internship")), "location": str(self.option("location", "India"))}
        page_count = None
        for page in range(1, max_pages + 1):
            query = dict(params)
            query["page"] = page
            url = f"{SEARCH_URL}?{urlencode(query)}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
            except FetchError as exc:
                errors.append(str(exc))
                break
            results = data.get("results") or [] if isinstance(data, dict) else []
            if not results:
                break
            for result in results:
                postings.append(self._normalise(result))
            page_count = data.get("page_count")
            if len(results) < PAGE_SIZE:
                break
            if page_count is not None and page >= int(page_count):
                break

        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, result: dict) -> JobPosting:
        company = result.get("company") or {}
        company_name = company.get("name") if isinstance(company, dict) else str(company or "")

        locations = [
            str(loc.get("name"))
            for loc in (result.get("locations") or [])
            if isinstance(loc, dict) and loc.get("name")
        ]
        location = ", ".join(locations)

        levels = [
            str(level.get("name"))
            for level in (result.get("levels") or [])
            if isinstance(level, dict) and level.get("name")
        ]

        refs = result.get("refs") or {}
        url = refs.get("landing_page") if isinstance(refs, dict) else ""

        remote_signal = any("remote" in loc.lower() or "flexible" in loc.lower() for loc in locations)

        return JobPosting(
            source=self.name,
            job_id=str(result.get("id") or url or result.get("name") or ""),
            company=company_name or "",
            title=result.get("name") or "",
            url=url or "",
            apply_url=url or "",
            location=location,
            description=html_to_text(result.get("contents") or ""),
            employment_type=", ".join(levels),
            published_at=str(result.get("publication_date") or ""),
            is_remote=True if remote_signal else None,
            raw=result,
        )
