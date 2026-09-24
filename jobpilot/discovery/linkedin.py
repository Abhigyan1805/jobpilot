"""Optional read-only LinkedIn listing reader.

This adapter reads LinkedIn's *public, unauthenticated* guest job-search
results. It **never** logs in, never authenticates, never applies, and never
touches any account. It runs at a deliberately low rate and degrades gracefully:
any block, redirect to a sign-in wall, or shape change is reported as a source
error and the pipeline falls back to the ATS sources.

A single generic ``intern`` keyword over one page fetched only about ten
unrelated listings, so the reader now runs a *configurable list of target
queries* (``[linkedin].keywords``), pages each a few times, and merges and
de-duplicates the results by LinkedIn's own job id. A failure in one query is
recorded in ``query_errors`` but never fails the adapter; only a total failure
raises. The request rate stays deliberately low (``requests_per_second``) and
each query's contribution is recorded in ``query_counts`` so the coverage gain
is visible.

Honest limitation: reading LinkedIn this way is against LinkedIn's Terms of
Service and is best-effort. It may stop working at any time. It is disabled by
default; enable it only with that understanding.
"""

from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

from jobpilot.discovery.base import SourceAdapter, string_list
from jobpilot.htmlutil import clean_whitespace
from jobpilot.http import FetchError, fetch_text
from jobpilot.models import JobPosting

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
VIEW_RE = re.compile(r"/jobs/view/(?:[^/?#]*?-)?(\d+)")
JOB_ID_RE = re.compile(r"urn:li:jobPosting:(\d+)")

# HTML void elements never carry an end tag. The card parser tracks nesting
# depth to know when a result card closes; counting a void element (a <br>,
# <img> or <input> inside a card) in that depth makes it drift upward and the
# parser stops recognising later cards. They are excluded from the depth count.
_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


class _LinkedInParser(HTMLParser):
    """Tolerant parser for the guest search-result cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict] = []
        self._cur: dict | None = None
        self._depth = 0
        self._card_depth = -1
        self._capture: str | None = None
        self._capture_tag: str | None = None
        self._capture_depth = -1
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_d = {k: v for k, v in attrs}
        classes = (attrs_d.get("class") or "").split()
        urn = attrs_d.get("data-entity-urn", "")
        if self._cur is None and urn:
            m = JOB_ID_RE.search(urn)
            if m:
                self._cur = {"job_id": m.group(1), "url": "", "title": "", "company": "", "location": "", "posted": ""}
                self._card_depth = self._depth
        elif self._cur is not None:
            if tag == "a" and "base-card__full-link" in classes and not self._cur["url"]:
                self._cur["url"] = attrs_d.get("href", "")
            elif tag == "h3" and "base-search-card__title" in classes:
                self._start_capture("title", tag)
            elif tag == "h4" and "base-search-card__subtitle" in classes:
                self._start_capture("company", tag)
            elif (tag == "span" or tag == "div") and "job-search-card__location" in classes:
                self._start_capture("location", tag)
            elif tag == "time":
                self._cur["posted"] = attrs_d.get("datetime", "")
        if tag not in _VOID_ELEMENTS:
            self._depth += 1

    def _start_capture(self, field, tag):
        self._capture = field
        self._capture_tag = tag
        self._capture_depth = self._depth
        self._buf = []

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            return
        self._depth -= 1
        if self._capture is not None and tag == self._capture_tag and self._depth == self._capture_depth:
            self._flush()
            self._capture = None
            self._capture_tag = None
        if self._cur is not None and self._depth == self._card_depth and tag == "div":
            self.cards.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._capture and self._cur is not None:
            self._buf.append(data)

    def _flush(self):
        if self._cur is None:
            return
        text = clean_whitespace("".join(self._buf))
        if self._capture in self._cur and text:
            self._cur[self._capture] = text
        self._buf = []

    def close(self):
        super().close()
        if self._capture:
            self._flush()
            self._capture = None
        if self._cur is not None:
            self.cards.append(self._cur)
            self._cur = None


def parse_search_html(markup: str) -> list[dict]:
    parser = _LinkedInParser()
    parser.feed(markup)
    parser.close()
    return parser.cards


class LinkedInAdapter(SourceAdapter):
    name = "linkedin"
    requires_tokens = False

    def fetch(self) -> list[JobPosting]:
        cfg = self.config.linkedin
        max_pages = int(self.option("max_pages", cfg.max_pages))
        max_results = int(self.option("max_results", cfg.max_results))
        interval = 1.0 / max(cfg.requests_per_second, 0.05)
        location = self._q(self.option("location", cfg.location))
        queries = string_list(self.option("keywords", cfg.keywords))

        postings: list[JobPosting] = []
        seen: set[str] = set()
        errors: list[str] = []
        sign_in_wall = False
        for query in queries:
            contributed = 0
            label = f"keywords={query}"
            for page in range(max_pages):
                url = f"{SEARCH_URL}?keywords={self._q(query)}&location={location}&start={page * 10}"
                try:
                    markup = fetch_text(
                        url,
                        timeout=float(cfg.timeout),
                        retries=1,
                        limiter=self.limiter,
                        headers={"Accept": "text/html"},
                    )
                except Exception as exc:  # noqa: BLE001 - one query must not fail the adapter
                    message = f"{type(exc).__name__}: {exc}"
                    self.query_errors[label] = message
                    errors.append(f"{query}: {message}")
                    break
                time.sleep(interval)

                cards = parse_search_html(markup)
                if not cards:
                    if page == 0 and ("authwall" in markup or "sign in" in markup.lower()):
                        message = "linkedin returned a sign-in wall; source unavailable"
                        self.query_errors[label] = message
                        errors.append(message)
                        sign_in_wall = True
                    elif page == 0:
                        message = "no cards parsed (shape change or empty result)"
                        self.query_errors[label] = message
                        errors.append(f"{query}: {message}")
                    break

                for card in cards:
                    jid = card.get("job_id")
                    if not jid or jid in seen:
                        continue
                    seen.add(jid)
                    postings.append(
                        JobPosting(
                            source=self.name,
                            job_id=jid,
                            company=card.get("company", ""),
                            title=card.get("title", ""),
                            url=urljoin("https://www.linkedin.com", card.get("url", "")),
                            apply_url=urljoin("https://www.linkedin.com", card.get("url", "")),
                            location=card.get("location", ""),
                            description="",
                            employment_type="",
                            published_at=card.get("posted", ""),
                            is_remote=("remote" in card.get("location", "").lower()) or None,
                            raw=card,
                        )
                    )
                    contributed += 1
                    if len(postings) >= max_results:
                        break
                if len(postings) >= max_results:
                    break
            self.query_counts[label] = contributed
            if sign_in_wall or len(postings) >= max_results:
                break

        if not postings and errors:
            raise FetchError("; ".join(errors))
        return postings

    @staticmethod
    def _q(value: str) -> str:
        from urllib.parse import quote

        return quote(str(value))
