"""Unstop public opportunity-search adapter (no authentication).

Endpoint verified live:

    GET https://unstop.com/api/public/opportunity/search-result?opportunity=internships&page=N
    GET https://unstop.com/api/public/opportunity/search-result?opportunity=internships&page=N&searchTerm=ai

Unstop's ``robots.txt`` explicitly allows ``/api/public/*`` (and allows the
major AI crawlers), so this is the clearest sanctioned public API among the
India platforms. The live ``search-result`` feed carries ~10,000 internships
and paginates 10 rows per page. Rows expose ``start_date``/``end_date``,
``region``/``locations``, ``required_skills`` and ``organisation``, which this
adapter maps onto the shared posting shape.

The generic feed is recency-sorted and dominated by sales/marketing/BD roles:
in 300 rows it surfaced no AI/ML internship at all. The API also accepts a
server-side ``searchTerm`` keyword filter, so this adapter runs the generic feed
*and* one ``searchTerm`` query per configured keyword, then merges and
de-duplicates by Unstop's own id. This is the typed-slice-plus-broader-query
pattern the other search adapters use: the keyword slice is a high-precision
path, never the only one. A failure in one query is recorded in ``query_errors``
but never fails the adapter, and each query's contribution is recorded in
``query_counts``. The generic feed also repeats rows across pages; every page is
still fetched, and de-duplicating here only removes the repeated postings from
the returned set.
"""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter, string_list
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

SEARCH_URL = "https://unstop.com/api/public/opportunity/search-result"
PAGE_SIZE = 10

#: Default ``searchTerm`` slices. Each was verified live to return real rows
#: (e.g. "machine learning" ~619, "artificial intelligence" ~267,
#: "data science" ~1826, "ai" ~2122, "software engineer" ~4380). Override with
#: ``[sources.unstop] keywords = [...]``.
DEFAULT_KEYWORDS = (
    "machine learning",
    "artificial intelligence",
    "ai",
    "data science",
    "software engineer",
)


class UnstopAdapter(SourceAdapter):
    name = "unstop"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        seen: set[str] = set()
        errors: list[str] = []
        ok = False
        max_pages = int(self.option("max_pages", 2))
        keyword_pages = int(self.option("keyword_max_pages", 1))
        opportunity = str(self.option("opportunity", "internships"))
        keywords = string_list(self.option("keywords", DEFAULT_KEYWORDS))

        generic, generic_error = self._run_query(opportunity, max_pages, search_term=None)
        self.query_counts["generic feed"] = self._merge(generic, postings, seen)
        if generic_error:
            self.query_errors["generic feed"] = generic_error
            errors.append(f"generic: {generic_error}")
        else:
            ok = True

        for term in keywords:
            rows, error = self._run_query(opportunity, keyword_pages, search_term=term)
            label = f"searchTerm={term}"
            self.query_counts[label] = self._merge(rows, postings, seen)
            if error:
                self.query_errors[label] = error
                errors.append(f"{term}: {error}")
            else:
                ok = True

        if not ok and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _run_query(self, opportunity: str, max_pages: int, *, search_term: str | None) -> tuple[list[JobPosting], str]:
        postings: list[JobPosting] = []
        for page in range(1, max_pages + 1):
            params = {"opportunity": opportunity, "page": page}
            if search_term:
                params["searchTerm"] = search_term
            url = f"{SEARCH_URL}?{urlencode(params)}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)), limiter=self.limiter)
            except FetchError as exc:
                return postings, f"page {page}: {exc}"
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
        return postings, ""

    @staticmethod
    def _merge(rows: list[JobPosting], merged: list[JobPosting], seen: set[str]) -> int:
        """Append rows not already seen; return how many were newly added."""
        added = 0
        for posting in rows:
            key = posting.job_id or posting.stable_id
            if key in seen:
                continue
            seen.add(key)
            merged.append(posting)
            added += 1
        return added

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
        return f"Internship starts: {str(start).split('T')[0]} - {str(end).split('T')[0]}"
