"""Lever public postings adapter (no authentication)."""

from __future__ import annotations

from urllib.parse import urlencode

from jobpilot.discovery.base import SourceAdapter
from jobpilot.htmlutil import html_to_text
from jobpilot.http import FetchError, fetch_json
from jobpilot.models import JobPosting

POSTINGS_URL = "https://api.lever.co/v0/postings/{token}"


class LeverAdapter(SourceAdapter):
    name = "lever"

    def fetch(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        errors: list[str] = []
        for token in self.tokens:
            # Lever documents a `commitment` filter (case-sensitive). Use the
            # board's typed field server-side instead of matching titles.
            params = {"mode": "json"}
            commitment = self.option("commitment", "Intern")
            if commitment:
                params["commitment"] = str(commitment)
            url = f"{POSTINGS_URL.format(token=token)}?{urlencode(params)}"
            try:
                data = fetch_json(url, timeout=float(self.option("timeout", 20)))
            except FetchError as exc:
                errors.append(f"{token}: {exc}")
                continue
            if not isinstance(data, list):
                errors.append(f"{token}: unexpected response shape")
                continue
            for job in data:
                commitment_value = (job.get("categories") or {}).get("commitment", "") or ""
                if not self.keep_intern(commitment_value):
                    continue
                postings.append(self._normalise(token, job))
        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    def _normalise(self, token: str, job: dict) -> JobPosting:
        categories = job.get("categories") or {}
        location = categories.get("location", "") or ""
        commitment = categories.get("commitment", "") or ""
        team = categories.get("team", "") or ""
        description = "\n".join(
            p for p in [job.get("descriptionPlain", ""), job.get("additionalPlain", "")] if p
        )
        if not description and job.get("descriptionHtml"):
            description = html_to_text(job["descriptionHtml"])
        return JobPosting(
            source=self.name,
            job_id=str(job.get("id")),
            company=token,
            title=job.get("text", "") or "",
            url=job.get("hostedUrl", "") or "",
            apply_url=(job.get("applyUrl") or job.get("hostedUrl") or ""),
            location=location,
            description=description.strip(),
            employment_type=commitment,
            published_at=str(job.get("createdAt", "") or ""),
            is_remote=("remote" in location.lower()) or None,
            raw={**job, "_team": team},
        )
