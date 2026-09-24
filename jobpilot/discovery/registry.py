"""Build and run every configured discovery adapter.

Every source is pluggable behind :class:`SourceAdapter`. A source failure is
captured as an :class:`FetchOutcome` error and never aborts the run.
"""

from __future__ import annotations

from jobpilot.config import Config, SourceConfig
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
from jobpilot.robots import RobotsGate

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


def build_adapters(config: Config, robots: RobotsGate | None = None) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    for name, cls in ADAPTERS.items():
        source_config = config.sources.get(name)
        if name == "linkedin":
            # The optional reader is gated by [linkedin].enabled, not by a
            # [sources.linkedin] entry (it is deliberately absent from the
            # default sources). Register it on demand so the documented toggle
            # actually enables the adapter; a [sources.linkedin] entry, when
            # present, still controls it through its own `enabled` flag.
            if not config.linkedin.enabled:
                continue
            if source_config is None:
                source_config = SourceConfig(name="linkedin", enabled=True)
        if source_config is None:
            continue
        limiter = RateLimiter(float(source_config.options.get("min_interval_seconds", 0.0)))
        adapters.append(cls(source_config, config, limiter, robots=robots))
    return adapters


def discover(config: Config) -> tuple[list[JobPosting], list[FetchOutcome]]:
    """Run all adapters, returning de-duplicated postings and per-source outcomes.

    One :class:`RobotsGate` is created per run and shared by every adapter, so
    each source host's robots.txt is read at most once and its verdict is
    cached for the whole run. The gate fails closed: a host whose policy cannot
    be read is skipped rather than fetched.
    """
    robots = (
        RobotsGate(agent=config.robots.agent, timeout=float(config.robots.timeout))
        if config.robots.enabled
        else None
    )
    outcomes: list[FetchOutcome] = []
    merged: dict[str, JobPosting] = {}
    for adapter in build_adapters(config, robots=robots):
        outcome = adapter.fetch_safe()
        outcomes.append(outcome)
        for posting in outcome.postings:
            merged.setdefault(posting.stable_id, posting)
    return list(merged.values()), outcomes
