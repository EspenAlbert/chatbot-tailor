"""Discover candidate pages under one URL.

Collects same-origin URLs from `/llms.txt`, `/sitemap.xml` and the sitemaps named in
`robots.txt`, and the start page's anchors, then classifies each path and writes
`cache/chatbot-tailor/{yyyy-mm-dd}/{host}/candidates.yaml`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from model_lib import Event, dump
from model_lib.constants import FileFormat
from pydantic import Field, model_validator
from zero_3rdparty import file_utils

from chatbot_tailor import links, robots, sitemaps, urls
from chatbot_tailor.http import Get, http_get

MAX_CANDIDATES = 300
MAX_SITEMAPS = 20

KEEP_WORDS = ("product", "pricing", "faq", "support", "docs", "help", "about", "solutions", "features")
DROP_WORDS = ("careers", "jobs", "legal", "privacy", "terms", "cookie", "login", "signup")

_DATE_SEGMENT = re.compile(r"^\d{4}(?:[-/]\d{2}){0,2}$")
_URL = re.compile(r"https?://[^\s)\]\"'<>]+")
_TRAILING = ".,;:"


class Hint(StrEnum):
    KEEP = "keep"
    MAYBE = "maybe"
    DROP = "drop"


_ORDER = (Hint.KEEP, Hint.MAYBE, Hint.DROP)
_RANK = {str(hint): rank for rank, hint in enumerate(_ORDER)}


class Candidate(Event):
    url: str
    path: str
    hint: Hint


class DiscoverInput(Event):
    url: str
    workspace_root: Path
    today: date | None = None

    @model_validator(mode="after")
    def _check_url(self) -> Self:
        split = urlsplit(self.url)
        if split.scheme not in {"http", "https"} or not split.hostname:
            raise ValueError("url must be http or https")
        return self


class DiscoverResult(Event):
    path: Path
    counts: dict[Hint, int] = Field(default_factory=dict)


def classify(url: str) -> Hint:
    path = urls.path_of(url).lower()
    if any(word in path for word in DROP_WORDS) or _is_blog_with_date(path):
        return Hint.DROP
    if any(word in path for word in KEEP_WORDS):
        return Hint.KEEP
    return Hint.MAYBE


def _is_blog_with_date(path: str) -> bool:
    segments = [segment for segment in path.split("/") if segment]
    if "blog" not in segments:
        return False
    return any(_DATE_SEGMENT.match(segment) for segment in segments)


def llms_urls(text: str) -> list[str]:
    return [url.rstrip(_TRAILING) for url in _URL.findall(text)]


def discover(data: DiscoverInput, *, get: Get = http_get) -> DiscoverResult:
    start = urls.strip_query_fragment(data.url)
    base = urls.origin(start)
    collected: dict[str, Candidate] = {}

    def add(url: str, hint: Hint) -> None:
        normalized = urls.strip_query_fragment(url)
        if not urls.same_origin(normalized, start) or normalized in collected:
            return
        collected[normalized] = Candidate(url=normalized, path=urls.path_of(normalized), hint=hint)

    add(start, Hint.KEEP)
    if llms := _fetch_text(get, f"{base}/llms.txt"):
        for url in llms_urls(llms):
            add(url, Hint.KEEP)
    rules = robots.parse(_fetch_text(get, f"{base}/robots.txt"))
    for loc in _sitemap_locs(get, base, rules):
        add(loc, classify(loc))
    if html := _fetch_text(get, start):
        for url in links.same_origin_links(html, start):
            add(url, classify(url))

    ordered = sorted(
        (candidate for candidate in collected.values() if robots.allows(rules, candidate.url)),
        key=lambda candidate: _RANK[str(candidate.hint)],
    )[:MAX_CANDIDATES]
    path = urls.candidates_path(data.workspace_root, data.today or datetime.now().astimezone().date(), data.url)
    file_utils.ensure_parents_write_text(path, dump.dump_as_str(ordered, FileFormat.yaml))
    counts = {hint: sum(1 for candidate in ordered if candidate.hint == hint) for hint in _ORDER}
    return DiscoverResult(path=path, counts=counts)


def _sitemap_locs(get: Get, base: str, rules: RobotFileParser) -> list[str]:
    queue = [f"{base}/sitemap.xml", *robots.sitemaps(rules)]
    seen: set[str] = set()
    locs: list[str] = []
    while queue and len(seen) < MAX_SITEMAPS:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen:
            continue
        seen.add(sitemap_url)
        text = _fetch_text(get, sitemap_url)
        if text is None:
            continue
        parsed = sitemaps.parse(text)
        if parsed.is_index:
            queue.extend(parsed.locs)
        else:
            locs.extend(parsed.locs)
    return locs


def _fetch_text(get: Get, url: str) -> str | None:
    try:
        response = get(url)
    except (httpx.HTTPError, UnicodeError):
        return None
    if response.status_code != 200:
        return None
    return response.text
