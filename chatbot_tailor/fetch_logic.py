"""Fetch the chosen pages and the start page's brand hints.

Reads `pages.yaml` (a list of URLs) beside `candidates.yaml`, fetches each URL with the
copied anki-nuggets extractor into `pages/{slug}.md`, and reads the start page's HTML into
`brand.yaml`, saving an SVG icon to `brand/favicon.svg`.
"""

from __future__ import annotations

from pathlib import Path

from model_lib import Event, dump, parse
from model_lib.constants import FileFormat
from model_lib.errors import PayloadError
from pydantic import Field
from zero_3rdparty import file_utils

from chatbot_tailor import brand, fetch_page, urls
from chatbot_tailor.fetch_page import Page, Skipped
from chatbot_tailor.http import Get, get_bytes, get_text, http_get

MIN_WORDS = 150
EXIT_EMPTY = 1
EXIT_INPUT = 2
PAGES_FILE = "pages.yaml"
CANDIDATES_FILE = "candidates.yaml"
PAGES_DIR = "pages"
BRAND_FILE = "brand.yaml"


class FetchResult(Event):
    exit_code: int
    written: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    brand_path: Path | None = None
    detail: str = ""


def slugs(page_urls: list[str]) -> list[str]:
    taken: set[str] = set()
    result: list[str] = []
    for url in page_urls:
        base = urls.slug_from_url(url) or "index"
        slug = base
        suffix = 2
        while slug in taken:
            slug = f"{base}-{suffix}"
            suffix += 1
        taken.add(slug)
        result.append(slug)
    return result


def start_url(directory: Path) -> str | None:
    candidates = _load_list(directory / CANDIDATES_FILE) or []
    if candidates and isinstance(candidates[0], dict) and (url := candidates[0].get("url")):
        return url
    pages = _load_list(directory / PAGES_FILE) or []
    if pages and isinstance(pages[0], str):
        return pages[0]
    return None


def fetch(directory: Path, *, get: Get = http_get) -> FetchResult:
    pages = _load_pages(directory)
    if pages is None:
        return FetchResult(exit_code=EXIT_INPUT, detail=f"{PAGES_FILE}: missing or not a list of URLs")
    written: list[str] = []
    skipped: list[str] = []
    for url, slug in zip(pages, slugs(pages), strict=True):
        fetched = fetch_page.fetch_page(url, get=get)
        match fetched:
            case Skipped(url=page_url, reason=reason):
                skipped.append(f"{page_url}: {reason}")
            case Page(url=page_url, word_count=count) if count < MIN_WORDS:
                skipped.append(f"{page_url}: under {MIN_WORDS} words ({count})")
            case Page(source=source):
                file_utils.ensure_parents_write_text(directory / PAGES_DIR / f"{slug}.md", source)
                written.append(slug)
    brand_path = _write_brand(directory, get)
    if written:
        return FetchResult(exit_code=0, written=written, skipped=skipped, brand_path=brand_path)
    return FetchResult(exit_code=EXIT_EMPTY, skipped=skipped, brand_path=brand_path, detail="no pages survived")


def _write_brand(directory: Path, get: Get) -> Path:
    hints = brand.HtmlHints()
    if (start := start_url(directory)) and (html := get_text(get, start)):
        hints = brand.parse_html(html, start)
    stylesheet_css = [text for url in hints.stylesheet_urls if (text := get_text(get, url))]
    favicon_bytes = get_bytes(get, hints.favicon_url) if hints.favicon_url else None
    if favicon_bytes:
        favicon_path = directory / brand.FAVICON_PATH
        favicon_path.parent.mkdir(parents=True, exist_ok=True)
        favicon_path.write_bytes(favicon_bytes)
    result = brand.build_brand(hints, stylesheet_css, brand.FAVICON_PATH if favicon_bytes else None)
    path = directory / BRAND_FILE
    file_utils.ensure_parents_write_text(path, dump.dump_as_str(result.model_dump(exclude_none=True), FileFormat.yaml))
    return path


def _load_pages(directory: Path) -> list[str] | None:
    loaded = _load_list(directory / PAGES_FILE)
    if loaded is None or not all(isinstance(entry, str) for entry in loaded):
        return None
    return loaded


def _load_list(path: Path) -> list | None:
    if not path.exists():
        return None
    try:
        return parse.parse_list(path)
    except PayloadError:
        return None
