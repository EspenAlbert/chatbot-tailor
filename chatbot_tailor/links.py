"""Absolute same-origin links on a page."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from chatbot_tailor import urls

_HTTP_SCHEMES = frozenset({"http", "https"})


class _AnchorScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        if href := dict(attrs).get("href"):
            self.hrefs.append(href)


def same_origin_links(html: str, page: str) -> list[str]:
    parser = _AnchorScan()
    parser.feed(html)
    parser.close()
    found: list[str] = []
    for href in parser.hrefs:
        absolute = urljoin(page, href)
        if urlsplit(absolute).scheme not in _HTTP_SCHEMES:
            continue
        if not urls.same_origin(absolute, page):
            continue
        found.append(absolute)
    return found
