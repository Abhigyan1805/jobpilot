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

    @property
    def ok(self) -> bool:
        return not self.error and not self.skipped


class SourceAdapter(ABC):
    """Fetch internship postings from one public source.

    Implementations must never authenticate, must be read-only, and must raise
    nothing that escapes :meth:`fetch_safe`; a source failure is isolated.
    """

    name: str = "base"
    #: Board tokens or search parameters come from config; no default tokens.
    requires_tokens: bool = True
    #: Default for the ``intern_only`` typed-field filter. Subclasses whose
    #: structured employment-type field is not a reliable intern signal set
    #: this to False; callers can still override it per source in config.
    intern_only_default: bool = True

    def __init__(self, source_config: SourceConfig, config: Config, limiter: RateLimiter | None = None):
        self.source_config = source_config
        self.config = config
        self.limiter = limiter or RateLimiter(0.0)

    @property
    def tokens(self) -> list[str]:
        return list(self.source_config.tokens)

    def option(self, key: str, default=None):
        return self.source_config.options.get(key, default)

    def intern_only(self) -> bool:
        """Whether to drop postings whose structured employment type is clearly not an internship."""
        value = self.option("intern_only", self.intern_only_default)
        if isinstance(value, str):
            return value.strip().lower() not in ("false", "0", "no", "off")
        return bool(value)

    def keep_intern(self, employment_type: str) -> bool:
        """Keep a posting based on its *structured* employment type.

        A source's own typed field (``commitment``, ``employmentType``,
        ``employment_type``) is authoritative for internship status. Title text
        is never used to infer it here. An absent typed value is kept so the
        shared hard filter can decide; a present, clearly non-intern typed value
        is dropped when ``intern_only`` is on.
        """
        if not self.intern_only():
            return True
        value = (employment_type or "").strip().lower()
        if not value:
            return True
        return "intern" in value

    @abstractmethod
    def fetch(self) -> list[JobPosting]:
        """Return normalised postings. May raise; callers use fetch_safe."""

    def fetch_safe(self) -> FetchOutcome:
        if not self.source_config.enabled:
            return FetchOutcome(self.name, skipped=True, error="source disabled")
        if self.requires_tokens and not self.tokens:
            return FetchOutcome(self.name, skipped=True, error="no board tokens configured")
        try:
            return FetchOutcome(self.name, postings=self.fetch())
        except Exception as exc:  # noqa: BLE001 - one source must not abort the run
            return FetchOutcome(self.name, error=f"{type(exc).__name__}: {exc}")
