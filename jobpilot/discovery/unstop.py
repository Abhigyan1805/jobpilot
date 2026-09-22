"""Unstop public opportunity-search adapter (no authentication).

Endpoint verified live:

    GET https://unstop.com/api/public/opportunity/search-result?opportunity=internships&page=N

Unstop's ``robots.txt`` explicitly allows ``/api/public/*`` (and allows the
major AI crawlers), so this is the clearest sanctioned public API among the
India platforms. The live ``search-result`` feed carries ~10,000 internships
and paginates 10 rows per page. Rows expose ``start_date``/``end_date``,
``region``/``locations``, ``required_skills`` and ``organisation``, which this
adapter maps onto the shared posting shape.
"""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://unstop.com/api/public/opportunity/search-result"
PAGE_SIZE = 10


class UnstopAdapter(SourceAdapter):
    name = "unstop"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        max_pages = int(self.option("max_pages", 2))
        opportunity = str(self.option("opportunity", "internships"))
        for page in range(1, max_pages + 1):
            url = f"{SEARCH_URL}?{urlencode({'opportunity': opportunity, 'page': page})}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
            except FetchError as exc:
                errors.append(str(exc))
                break
            root = data.get("data") if isinstance(data, dict) else None
            rows = (root.get("data") if isinstance(root, dict) else root) or []
            if not rows:
                break
            for row in rows:
                status = str(row.get("status") or "").upper()
                if status and status != "LIVE":
                    continue
                postings.append(self._normalise(row))
            last_page = root.get("last_page") if isinstance(root, dict) else None
            if len(rows) < PAGE_SIZE:
                break
            if last_page and page >= int(last_page):
                break

        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, row: dict) -> JobPosting:
        organisation = row.get("organisation")
        if isinstance(organisation, dict):
            company = organisation.get("name") or ""
        else:
            company = str(organisation or "")

        seo_url = row.get("seo_url") or ""
        public_url = row.get("public_url") or ""
        if seo_url:
            url = seo_url
        elif public_url:
            url = public_url if public_url.startswith("http") else f"https://unstop.com/{public_url.lstrip('/')}"
        else:
            url = ""

        region = str(row.get("region") or "")
        location = self._location(region, row.get("locations"))

        work_functions = [
            str(wf.get("work_function_name"))
            for wf in (row.get("workfunction") or [])
            if isinstance(wf, dict) and wf.get("work_function_name")
        ]
        skills = [
            str(s.get("skill_name") or s.get("skill"))
            for s in (row.get("required_skills") or [])
            if isinstance(s, dict) and (s.get("skill_name") or s.get("skill"))
        ]
        parts: list[str] = []
        window = self._window_text(row.get("start_date"), row.get("end_date"))
        if window:
            parts.append(window)
        if work_functions:
            parts.append("Work function: " + ", ".join(work_functions))
        details = html_to_text(row.get("details") or "")
        if details:
            parts.append(details)
        if skills:
            parts.append("Required skills: " + ", ".join(skills))

        subtype = str(row.get("subtype") or "")
        employment_type = "Internship" if subtype == "internships" else str(row.get("type") or "")

        return JobPosting(
            source=self.name,
            job_id=str(row.get("id") or row.get("short_id") or url),
            company=company,
            title=row.get("title") or "",
            url=url,
            apply_url=url,
            location=location,
            description="\n".join(parts),
            employment_type=employment_type,
            published_at=str(row.get("approved_date") or row.get("updated_at") or ""),
            is_remote=("online" in region.lower() or "remote" in region.lower()) or None,
            raw=row,
        )

    @staticmethod
    def _location(region: str, locations) -> str:
        place = ""
        if isinstance(locations, list):
            names = []
            for loc in locations:
                if isinstance(loc, dict):
                    name = loc.get("name") or loc.get("city") or loc.get("label")
                    if name:
                        names.append(str(name))
                elif loc:
                    names.append(str(loc))
            place = ", ".join(names)
        region_label = region.replace("_", " ").strip().title()
        return ", ".join(p for p in [place, region_label] if p)

    @staticmethod
    def _window_text(start, end) -> str:
        """Reformat Unstop's typed dates into an explicit ISO range for the window filter.

        Only a real start-end pair is emitted: a lone date is left out so the
        posting stays "unknown window" (review-only) rather than being guessed.
        """
        if not start or not end:
            return ""
        return f"{str(start).split('T')[0]} - {str(end).split('T')[0]}"
