"""HTML to text helpers used by the discovery adapters.

Stdlib only: `html.unescape` for entities and a tiny `HTMLParser` subclass for
tag stripping, so no third-party dependency is required.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "td", "th", "table", "section", "article", "header", "footer", "blockquote",
}
_SKIP_TAGS = {"script", "style", "noscript", "svg"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS and self._parts:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = html.unescape(raw)
        raw = raw.replace("\xa0", " ")
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        return "\n".join(ln for ln in lines if ln).strip()


def html_to_text(markup: str | None) -> str:
    if not markup:
        return ""
    if "<" not in markup:
        # Already plain text or escaped text.
        return re.sub(r"[ \t]+", " ", html.unescape(markup)).strip()
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup must not abort a run
        return re.sub(r"<[^>]+>", " ", html.unescape(markup)).strip()
    return parser.text()


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
