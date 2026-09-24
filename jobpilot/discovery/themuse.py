"""The Muse public jobs adapter (no authentication).

Endpoints verified live:

    GET https://www.themuse.com/api/public/jobs?page=N&level=Internship&location=India
    GET https://www.themuse.com/api/public/jobs?page=N&location=India

Returns ``{page, page_count, items_per_page, total, results}`` (20 per page).
The API is public and free (500 requests/hour unauthenticated, 3,600 with a
registered key). ``level=Internship`` is a typed filter. ``location=India`` is
loose - the report observed a US role in the India results - so the shared hard
location filter validates each hit rather than trusting the parameter.

The typed ``level=Internship`` query is high precision but drops a genuine
internship the board mis-tags, so it is never the only path. A live probe shows
the endpoint ignores keyword/q/search/query/text, so the second path is the same
``location=India`` query without the ``level`` facet; it is merged with the
typed slice and deduplicated by source job id, and the shared hard filter
decides. Bounding the extra cost is a per-query page budget (``max_pages`` for
the typed query, ``broad_max_pages`` for the broader one).
"""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter, dedupe_postings
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://www.themuse.com/api/public/jobs"
PAGE_SIZE = 20


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TheMuseAdapter(SourceAdapter):
    name = "themuse"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        location = str(self.option("location", "India"))
        level = str(self.option("level", "Internship"))

        typed_params = {"location": location}
        if level:
            typed_params["level"] = level
        broad_params = {"location": location}

        postings, typed_error = self._run_query(typed_params, int(self.option("max_pages", 2)))
        ok = typed_error == ""
        errors = [f"typed: {typed_error}"] if typed_error else []
        if broad_params != typed_params:
            try:
                more, error = self._run_query(broad_params, int(self.option("broad_max_pages", 1)))
            except Exception as exc:  # noqa: BLE001 - a secondary query must never fail the adapter
                errors.append(f"broad: {type(exc).__name__}: {exc}")
            else:
                postings.extend(more)
                if error:
                    errors.append(f"broad: {error}")
                else:
                    ok = True

        if not ok and errors:
            raise FetchError("; ".join(errors))
        return dedupe_postings(postings)

    def _run_query(self, params: dict[str, str], max_pages: int) -> tuple[list[JobPosting], str]:
        postings: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            query = dict(params)
            query["page"] = page
            url = f"{SEARCH_URL}?{urlencode(query)}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
            except FetchError as exc:
                return postings, f"page {page}: {exc}"
            results = data.get("results") or [] if isinstance(data, dict) else []
            if not results:
                break
            for result in results:
                postings.append(self._normalise(result))
            if len(results) < PAGE_SIZE:
                break
            page_count = _as_int(data.get("page_count"))
            if page_count is not None and page >= page_count:
                break
        return postings, ""

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
