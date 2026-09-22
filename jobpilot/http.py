"""Tiny stdlib-only HTTP helpers with retries and optional rate limiting.

No third-party dependencies: `urllib` is always available, which keeps the
pipeline runnable on a bare Python install. A `requests` session is used only
when it happens to be importable, purely as an optimisation.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_HEADERS = {
    "User-Agent": "jobpilot/0.1 (read-only job discovery; contact: see config)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


class FetchError(Exception):
    """Raised when a fetch ultimately fails."""


@dataclass
class RateLimiter:
    """Minimum interval between requests to one source."""

    min_interval: float = 0.0
    _last: float = field(default=0.0, init=False)

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last = time.monotonic()


def fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    retries: int = 2,
    backoff: float = 1.5,
    limiter: RateLimiter | None = None,
) -> bytes:
    """GET a URL and return raw bytes, retrying transient failures."""
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        if limiter:
            limiter.wait()
        try:
            req = urllib.request.Request(url, headers=merged)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise FetchError(f"GET {url} failed after {retries + 1} attempts: {last_err}") from last_err


def fetch_json(url: str, **kwargs: Any) -> Any:
    raw = fetch(url, **kwargs)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"invalid JSON from {url}: {exc}") from exc


def fetch_text(url: str, **kwargs: Any) -> str:
    return fetch(url, **kwargs).decode("utf-8", "replace")


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")
