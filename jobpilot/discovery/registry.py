"""Build and run every configured discovery adapter.

Every source is pluggable behind :class:`SourceAdapter`. A source failure is
captured as an :class:`FetchOutcome` error and never aborts the run.
"""

from __future__ import annotations

from jobpilot.config import Config
from jobpilot.discovery.ashby import AshbyAdapter
from jobpilot.discovery.base import FetchOutcome, SourceAdapter
from jobpilot.discovery.greenhouse import GreenhouseAdapter
from jobpilot.discovery.himalayas import HimalayasAdapter
from jobpilot.discovery.lever import LeverAdapter
from jobpilot.discovery.linkedin import LinkedInAdapter
from jobpilot.discovery.localfile import LocalFileAdapter
from jobpilot.discovery.themuse import TheMuseAdapter
from jobpilot.discovery.unstop import UnstopAdapter
from jobpilot.discovery.workable import WorkableAdapter
from jobpilot.discovery.workable_global import WorkableGlobalAdapter
from jobpilot.http import RateLimiter
from jobpilot.models import JobPosting

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "workable": WorkableAdapter,
    "himalayas": HimalayasAdapter,
    "unstop": UnstopAdapter,
    "workable_global": WorkableGlobalAdapter,
    "themuse": TheMuseAdapter,
    "linkedin": LinkedInAdapter,
    "local": LocalFileAdapter,
}


def build_adapters(config: Config) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    for name, cls in ADAPTERS.items():
        source_config = config.sources.get(name)
        if source_config is None:
            continue
        if name == "linkedin" and not config.linkedin.enabled:
            continue
        limiter = RateLimiter(float(source_config.options.get("min_interval_seconds", 0.0)))
        adapters.append(cls(source_config, config, limiter))
    return adapters


def discover(config: Config) -> tuple[list[JobPosting], list[FetchOutcome]]:
    """Run all adapters, returning de-duplicated postings and per-source outcomes."""
    outcomes: list[FetchOutcome] = []
    merged: dict[str, JobPosting] = {}
    for adapter in build_adapters(config):
        outcome = adapter.fetch_safe()
        outcomes.append(outcome)
        for posting in outcome.postings:
            merged.setdefault(posting.stable_id, posting)
    return list(merged.values()), outcomes
