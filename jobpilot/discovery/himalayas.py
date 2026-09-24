"""Himalayas public job-search adapter (no authentication).

Endpoint verified live on 2026-09-21/22:

    GET https://himalayas.app/jobs/api/search?employment_type=Intern&country=India
    GET https://himalayas.app/jobs/api/search?q=intern&country=India

Returns ``{jobs: [...], totalCount, page, limit}`` (20 per page). The API is free
and needs no key. Himalayas' terms require a visible link back to himalayas.app
and the attribution "data sourced from Himalayas"; they also forbid republishing
its jobs to LinkedIn/Google Jobs/Jooble/Neuvoo. This adapter only reads the feed
and records the attribution in each posting's raw payload.

Only the **first page** of each query is fetched, and no ``page`` parameter is
sent. Himalayas' published policy disallows the paged API path
(``Disallow: /jobs*&page=``), which the enforced robots gate in
:mod:`jobpilot.http` honours per concrete request URL, so a ``page=N`` request
is refused before it leaves the process. Omitting the parameter requests the
first page directly and avoids the disallowed pattern entirely; paging is
deliberately not attempted and no per-host exception is carved out.

The typed ``employment_type=Intern`` query is high precision but drops a genuine
internship the board mis-tags (e.g. ``employmentType`` of ``Full Time``), so it
is never the only path: a keyword query (``q=intern`` by default) runs too and
the two result sets are merged and deduplicated by source job id. The merged
rows go through the shared hard filter, whose full-time rescue routes a
mis-tagged but intern-titled posting to human review rather than discarding it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter, dedupe_postings
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://himalayas.app/jobs/api/search"


def _iso(timestamp) -> str:
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(timestamp or "")


class HimalayasAdapter(SourceAdapter):
    name = "himalayas"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        country = str(self.option("country", "India"))
        employment_type = str(self.option("employment_type", "Intern"))
        worldwide = self.option("worldwide")

        def base_params() -> dict[str, str]:
            params = {"country": country}
            if worldwide:
                params["worldwide"] = "true"
            return params

        typed_params = base_params()
        typed_params["employment_type"] = employment_type

        keyword = self.option("keyword", "intern")
        keywords = [str(keyword)] if keyword else []

        postings, typed_error = self._run_query(typed_params)
        ok = typed_error == ""
        errors = [f"typed: {typed_error}"] if typed_error else []
        for term in keywords:
            params = base_params()
            params["q"] = str(term)
            try:
                more, error = self._run_query(params)
            except Exception as exc:  # noqa: BLE001 - a secondary query must never fail the adapter
                errors.append(f"{term}: {type(exc).__name__}: {exc}")
                continue
            postings.extend(more)
            if error:
                errors.append(f"{term}: {error}")
            else:
                ok = True

        if not ok and errors:
            raise FetchError("; ".join(errors))
        return dedupe_postings(postings)

    def _run_query(self, params: dict[str, str]) -> tuple[list[JobPosting], str]:
        """Fetch the first page of one query.

        The ``page`` parameter is never sent: ``Disallow: /jobs*&page=`` forbids
        the paged path, so requesting page 1 *without* the parameter is the only
        lawful request the adapter can make. It therefore never pages.
        """
        url = f"{SEARCH_URL}?{urlencode(params)}"
        try:
            data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
        except FetchError as exc:
            return [], str(exc)
        jobs = data.get("jobs") or [] if isinstance(data, dict) else []
        return [self._normalise(job) for job in jobs], ""

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
            raw={**job, "attribution": "data sourced from Himalayas"},
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
