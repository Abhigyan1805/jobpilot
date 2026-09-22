"""The link-out channel for sources whose terms forbid automation.

Some of the best sources for this search - Internshala above all - expressly
forbid automated extraction. jobpilot does not scrape them and does not
authenticate to them. Instead it:

* surfaces a configured search link per source, so a human can browse it;
* accepts a posting the human found there *by hand* and then runs the normal
  requirement extraction, matching, tailored resume and cover-letter generation
  on it, placing a ready-to-apply packet (with the direct link) in the review
  queue.

Anything from these sources is review-only: it is prepared and queued, never
auto-submitted. This is a deliberate product choice, not a missing feature.
"""

from __future__ import annotations

import hashlib

from jobpilot.config import Config, LinkOutSource, MANUAL_ONLY_SOURCES
from jobpilot.models import JobPosting


def is_manual_source(source: str) -> bool:
    """Whether a source is manual-only (link-out, never automated)."""
    return (source or "") in MANUAL_ONLY_SOURCES


def configured_sources(config: Config) -> list[LinkOutSource]:
    """Enabled link-out sources, in configuration order."""
    if not config.link_out.enabled:
        return []
    return [source for source in config.link_out.sources.values() if source.enabled]


def get_source(config: Config, name: str) -> LinkOutSource | None:
    return config.link_out.sources.get(name)


def _stable_job_id(url: str) -> str:
    digest = hashlib.sha1((url or "").strip().encode("utf-8")).hexdigest()[:16]
    return f"manual-{digest}"


def build_manual_posting(
    *,
    source: str,
    url: str,
    title: str,
    company: str,
    location: str = "",
    description: str = "",
    job_id: str = "",
    employment_type: str = "Internship",
    apply_url: str = "",
    published_at: str = "",
) -> JobPosting:
    """Build a posting a human found on a manual-only source.

    The source must be one of :data:`jobpilot.config.MANUAL_ONLY_SOURCES`; the
    direct posting URL is required so the review packet can carry it. When no
    job id is supplied, a stable id is derived from the URL so re-adding the
    same posting dedupes instead of queueing twice.
    """
    if not is_manual_source(source):
        raise ValueError(
            f"{source!r} is not a manual-only link-out source; expected one of "
            f"{', '.join(sorted(MANUAL_ONLY_SOURCES))}"
        )
    if not (url or "").strip():
        raise ValueError("a direct posting URL is required to add a manual posting")
    if not (title or "").strip():
        raise ValueError("a title is required to add a manual posting")

    return JobPosting(
        source=source,
        job_id=(job_id or _stable_job_id(url)),
        company=company or "",
        title=title,
        url=url,
        apply_url=apply_url or url,
        location=location or "",
        description=description or "",
        employment_type=employment_type or "",
        published_at=published_at or "",
        is_remote=None,
        raw={"manual": True, "link_out_source": source},
    )
