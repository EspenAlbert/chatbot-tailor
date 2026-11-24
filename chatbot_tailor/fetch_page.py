"""Download one HTML page and extract its main text as markdown.

Copied from py-play anki_nuggets/fetch_logic.py at 2d04330, without the GitHub, gist, image,
byline, and cache-path code. Writing pages to disk belongs to the fetch command.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
import trafilatura

from chatbot_tailor import headings, prose, urls

Get = Callable[[str], httpx.Response]


@dataclass(frozen=True)
class Page:
    url: str
    source: str
    """The page URL on line 1, then the extracted markdown with `{#id}` heading markers."""

    @property
    def word_count(self) -> int:
        return prose.prose_word_count(self.source)


@dataclass(frozen=True)
class Skipped:
    url: str
    reason: str
    status: int | None = None


def http_get(url: str) -> httpx.Response:
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url)
        response.read()
        return response


def fetch_page(url: str, *, get: Get = http_get) -> Page | Skipped:
    page = urls.page_url(url)
    try:
        response = get(page)
    except (httpx.HTTPError, UnicodeError) as exc:
        return Skipped(url=page, reason=str(exc))
    if response.status_code != 200:
        return Skipped(url=page, reason=f"HTTP {response.status_code}", status=response.status_code)
    markdown = page_markdown(response.text, page)
    if markdown is None:
        return Skipped(url=page, reason="empty extract")
    return Page(url=page, source=f"{page}\n{markdown.lstrip('\n')}")


def page_markdown(html: str, page: str) -> str | None:
    text = trafilatura.extract(html, url=page, output_format="markdown", include_comments=False)
    if text is None or not text.strip():
        return None
    metadata = trafilatura.extract_metadata(html)
    title = (getattr(metadata, "title", None) or "").strip()
    if title and not headings.has_heading(text, title):
        text = f"# {title}\n\n{text}"
    return headings.apply_html_ids(text, html)
