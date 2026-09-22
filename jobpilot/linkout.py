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

from jobpilot.config import Config, LinkOutSource
from jobpilot.models import JobPosting


def is_manual_source(config: Config, source: str) -> bool:
    """Whether a source is manual-only (link-out, never automated).

    Membership follows the loaded configuration, so a source the user adds
    under ``[link_out.sources.<name>]`` is manual-only end to end. The built-in
    defaults are always present in the default config.
    """
    return (source or "") in config.link_out.sources


def configured_sources(config: Config) -> list[LinkOutSource]:
    """Enabled link-out sources, in configuration order."""
    if not config.link_out.enabled:
        return []
    return [source for source in config.link_out.sources.values() if source.enabled]


def _stable_job_id(url: str) -> str:
    digest = hashlib.sha1((url or "").strip().encode("utf-8")).hexdigest()[:16]
    return f"manual-{digest}"


def build_manual_posting(
    config: Config,
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

    The source must be one of the link-out sources in the loaded configuration;
    the direct posting URL is required so the review packet can carry it. When
    no job id is supplied, a stable id is derived from the URL so re-adding the
    same posting dedupes instead of queueing twice.
    """
    if not is_manual_source(config, source):
        raise ValueError(
            f"{source!r} is not a manual-only link-out source; expected one of "
            f"{', '.join(sorted(config.link_out.sources))}"
        )
    if source not in {s.name for s in configured_sources(config)}:
        raise ValueError(
            f"{source!r} is a configured link-out source but is disabled; "
            "enable the [link_out] channel and the source to add postings from it"
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
