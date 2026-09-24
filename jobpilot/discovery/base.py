"""The single discovery interface every source adapter implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from jobpilot.config import Config, SourceConfig
from jobpilot.http import RateLimiter
from jobpilot.models import JobPosting


@dataclass
class FetchOutcome:
    source: str
    postings: list[JobPosting] = field(default_factory=list)
    error: str = ""
    skipped: bool = False
    #: Per-query discovery counts for adapters that run more than one query
    #: (e.g. LinkedIn's keyword set, Unstop's ``searchTerm`` slices). Keys are
    #: human-readable query labels; values are the *new* postings that query
    #: contributed after de-duplication. Empty for single-query adapters.
    query_counts: dict[str, int] = field(default_factory=dict)
    #: Per-query failures for multi-query adapters, keyed by the same query
    #: labels as :attr:`query_counts`. A partially degraded run still succeeds,
    #: but the failed query is visible here rather than masquerading as an empty
    #: result. Empty when every query succeeded.
    query_errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and not self.skipped


def string_list(value) -> list[str]:
    """Coerce a config value into a de-duplicated list of non-empty strings.

    Config may carry a single string (a legacy single-keyword setting) or a
    list/tuple of strings. Order is preserved and blank or duplicate entries are
    dropped, so an adapter can treat both shapes uniformly.
    """
    if value is None:
        items = []
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def dedupe_postings(postings: list[JobPosting]) -> list[JobPosting]:
    """Merge posting lists, keeping the first row seen for each source job id."""
    seen: set[str] = set()
    merged: list[JobPosting] = []
    for posting in postings:
        key = posting.job_id or posting.stable_id
        if key in seen:
            continue
        seen.add(key)
        merged.append(posting)
    return merged


class SourceAdapter(ABC):
    """Fetch internship postings from one public source.

    Implementations must never authenticate, must be read-only, and must raise
    nothing that escapes :meth:`fetch_safe`; a source failure is isolated.
    """

    name: str = "base"
    #: Board tokens or search parameters come from config; no default tokens.
    requires_tokens: bool = True

    def __init__(
        self,
        source_config: SourceConfig,
        config: Config,
        limiter: RateLimiter | None = None,
    ):
        self.source_config = source_config
        self.config = config
        self.limiter = limiter or RateLimiter(0.0)
        #: Populated by :meth:`fetch` for adapters that run several queries;
        #: :meth:`fetch_safe` copies it onto the :class:`FetchOutcome`.
        self.query_counts: dict[str, int] = {}
        #: Per-query failures, keyed like :attr:`query_counts`; copied onto the
        #: :class:`FetchOutcome` by :meth:`fetch_safe`.
        self.query_errors: dict[str, str] = {}

    @property
    def tokens(self) -> list[str]:
        return list(self.source_config.tokens)

    def option(self, key: str, default=None):
        return self.source_config.options.get(key, default)

    @abstractmethod
    def fetch(self) -> list[JobPosting]:
        """Return normalised postings. May raise; callers use fetch_safe."""

    def fetch_safe(self) -> FetchOutcome:
        if not self.source_config.enabled:
            return FetchOutcome(self.name, skipped=True, error="source disabled")
        if self.requires_tokens and not self.tokens:
            return FetchOutcome(self.name, skipped=True, error="no board tokens configured")
        try:
            postings = self.fetch()
        except Exception as exc:  # noqa: BLE001 - one source must not abort the run
            return FetchOutcome(self.name, error=f"{type(exc).__name__}: {exc}")
        return FetchOutcome(
            self.name,
            postings=postings,
            query_counts=dict(self.query_counts),
            query_errors=dict(self.query_errors),
        )
