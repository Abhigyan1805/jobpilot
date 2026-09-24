"""A robots.txt gate in front of every automated fetch.

jobpilot claims to be permission-respecting but, before this module, never
checked a site's published policy programmatically. This ports the cautious
checker from the MIT-licensed upstream project ``MadsLorentzen/ai-job-search``
(``tools/robots_check.py``), rewritten dependency-free on top of :mod:`urllib`
so jobpilot stays stdlib-only.

Rules implemented (RFC 9309), deliberately on the cautious side:

* longest-match wins; on equal specificity Disallow wins;
* a Disallow for either ``*`` or the configured agent (``jobpilot`` by default)
  blocks the fetch;
* blank lines inside a record do not end it;
* an empty body is a valid allow-all, but a non-empty body with no recognised
  directive is treated as unreadable (a misconfigured host answering 200 with an
  HTML error page must not silently grant permission);
* 404 means no published policy, which is permission;
* any other failure to read robots.txt leaves permission unconfirmed, and the
  fetch does not happen (fail closed).

The verdict is cached per host for the lifetime of the gate, so one gate created
per pipeline run checks each source host at most once.

MIT notice and attribution: the rule set and the wildcard matcher are derived
from ``tools/robots_check.py`` in MadsLorentzen/ai-job-search (MIT License,
Copyright (c) 2026 Mads Lorentzen). See the repository's LICENSE.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote, urlsplit

#: The product token jobpilot presents in its User-Agent and matches in a
#: robots.txt ``User-agent`` line.
DEFAULT_AGENT = "jobpilot"
USER_AGENT = "jobpilot/0.1 (read-only job discovery; robots gate)"
#: Fallback UA for reading robots.txt, mirroring upstream's browser-header
#: retry: some hosts answer a plain client with a WAF default while allowing a
#: browser client. It is used only to *read* the published policy, never to
#: override one.
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
_ROBOTS_FIELDS = ("user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host")


def is_robots_body(text: str) -> bool:
    """Does this actually look like a robots.txt?

    An empty or whitespace-only body IS a valid allow-all under RFC 9309 and
    stays allowed; a non-empty body with no recognised directive is unreadable.
    """
    if not text.strip():
        return True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if ":" in line and line.split(":", 1)[0].strip() in _ROBOTS_FIELDS:
            return True
    return False


def _groups(text: str) -> dict[str, list[tuple[bool, str]]]:
    """user-agent -> [(is_allow, pattern)], tolerating blank lines inside a record."""
    out: dict[str, list[tuple[bool, str]]] = {}
    agents: list[str] = []
    expect = True
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not expect:
                agents, expect = [], True
            agents.append(value.lower())
            out.setdefault(value.lower(), [])
        elif field in ("allow", "disallow") and agents:
            expect = False
            for agent in agents:
                out[agent].append((field == "allow", value))
    return out


def _match(pattern: str, path: str) -> int:
    """RFC 9309 wildcard match; returns match length or -1."""
    if pattern == "":
        return -1
    pattern = unquote(pattern)
    rx = "^" + "".join(
        ".*" if char == "*" else ("$" if char == "$" else re.escape(char)) for char in pattern
    )
    return len(pattern) if re.match(rx, path) else -1


def allowed(text: str, agent: str, path: str) -> bool:
    """Whether ``path`` is allowed for ``agent`` under a robots.txt ``text``."""
    groups = _groups(text)
    rules = groups.get(agent.lower()) or groups.get("*") or []
    best_len, best_allow = -1, True
    for is_allow, pattern in rules:
        length = _match(pattern, path)
        if length > best_len or (length == best_len and length >= 0 and not is_allow):
            best_len, best_allow = length, is_allow  # ties -> Disallow wins
    return True if best_len < 0 else best_allow


@dataclass(frozen=True)
class RobotsVerdict:
    allowed: bool
    reason: str


#: A robots.txt fetcher returns ``(body, http_status)`` and raises on any other
#: read failure. Injectable so the gate is testable without network access.
RobotsFetcher = Callable[[str], "tuple[str, int]"]


def _default_fetch(url: str, *, timeout: float) -> tuple[str, int]:
    last: Exception | None = None
    for user_agent in (USER_AGENT, BROWSER_AGENT):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
                return body, int(getattr(response, "status", 200) or 200)
        except urllib.error.HTTPError as exc:
            # A 404 is a real answer (no policy); every other status is a read
            # failure that leaves permission unconfirmed.
            if exc.code == 404:
                return "", 404
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
    raise last if last is not None else RuntimeError("robots.txt fetch failed")


class RobotsGate:
    """Check and cache robots.txt permission per host for one run."""

    def __init__(
        self,
        *,
        agent: str = DEFAULT_AGENT,
        timeout: float = 12.0,
        fetch: RobotsFetcher | None = None,
    ):
        self.agent = agent or DEFAULT_AGENT
        self.timeout = timeout
        self._fetch = fetch or (lambda url: _default_fetch(url, timeout=self.timeout))
        #: host -> (robots body or None, http status or None, error name or None).
        #: The robots.txt is read at most once per host per run; the path-specific
        #: verdict is then computed from the cached body.
        self._cache: dict[str, tuple[str | None, int | None, str | None]] = {}

    def verdict(self, url: str) -> RobotsVerdict:
        """Permission to fetch ``url``; robots.txt is read once per host per run."""
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host not in self._cache:
            self._cache[host] = self._fetch_host(parts)
        body, code, error = self._cache[host]
        return self._evaluate(parts, body, code, error)

    def _fetch_host(self, parts) -> tuple[str | None, int | None, str | None]:
        scheme = parts.scheme or "https"
        robots_url = f"{scheme}://{parts.netloc}/robots.txt"
        try:
            body, code = self._fetch(robots_url)
        except Exception as exc:  # noqa: BLE001 - any read failure is unconfirmed
            return None, None, type(exc).__name__
        return body, code, None

    def _evaluate(
        self,
        parts,
        body: str | None,
        code: int | None,
        error: str | None,
    ) -> RobotsVerdict:
        if error is not None:
            return RobotsVerdict(False, f"UNCONFIRMED ({error}) - robots.txt could not be read")
        if code == 404:
            return RobotsVerdict(True, "ALLOWED - no robots.txt published")
        if code != 200:
            return RobotsVerdict(False, f"UNCONFIRMED (HTTP {code}) - robots.txt could not be read")
        if not is_robots_body(body or ""):
            return RobotsVerdict(
                False, "UNCONFIRMED (HTTP 200 but the body is not a robots.txt)"
            )
        path = unquote(parts.path) or "/"
        if parts.query:
            path += "?" + parts.query
        for agent in (self.agent, "*"):
            if not allowed(body or "", agent, path):
                return RobotsVerdict(False, f"DISALLOWED for {agent} - robots.txt forbids this path")
        return RobotsVerdict(True, "ALLOWED - robots.txt permits this path")
