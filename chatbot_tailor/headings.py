"""Mark headings with the id the page already publishes.

Copied from py-play anki_nuggets/headings.py at 2d04330, without the GitHub slug path.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from chatbot_tailor import prose

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_ATX = re.compile(r"^(?P<marks>#{1,6})[ \t]+(?P<text>.*?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_TRAILING_MARKER = re.compile(r"\s*\{#[^}]+\}\s*$")
_SKIP_TAGS = frozenset({"script", "style"})


class _HeadingScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[int, str, str | None]] = []
        self._level = 0
        self._heading_id: str | None = None
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip or self._level:
            return
        if tag not in _HEADING_TAGS:
            return
        raw_id = dict(attrs).get("id")
        self._level = int(tag[1])
        self._heading_id = raw_id or None
        self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
            return
        if self._level and tag == f"h{self._level}":
            self.found.append((self._level, prose.collapse("".join(self._parts)), self._heading_id))
            self._level = 0

    def handle_data(self, data: str) -> None:
        if self._level and not self._skip:
            self._parts.append(data)


def _html_headings(html: str) -> list[tuple[int, str, str | None]]:
    parser = _HeadingScan()
    parser.feed(html)
    parser.close()
    return parser.found


def _atx_lines(markdown: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(markdown.splitlines()):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if match := _ATX.match(line):
            found.append((index, len(match.group("marks")), match.group("text")))
    return found


def _bare(text: str) -> str:
    return prose.collapse(_TRAILING_MARKER.sub("", text))


def has_heading(markdown: str, title: str) -> bool:
    target = prose.collapse(title)
    return any(_bare(text) == target for _index, _level, text in _atx_lines(markdown))


def _join(markdown: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    if markdown.endswith("\n"):
        return f"{body}\n"
    return body


def apply_html_ids(markdown: str, html: str) -> str:
    headings = _html_headings(html)
    used = [False] * len(headings)
    lines = markdown.splitlines()
    for index, level, text in _atx_lines(markdown):
        bare = _bare(text)
        marker = _take_html_id(headings, used, level, bare)
        if marker is None:
            continue
        lines[index] = f"{'#' * level} {bare} {{#{marker}}}"
    return _join(markdown, lines)


def _take_html_id(
    headings: list[tuple[int, str, str | None]],
    used: list[bool],
    level: int,
    text: str,
) -> str | None:
    for index, (heading_level, heading_text, heading_id) in enumerate(headings):
        if used[index] or heading_level != level or heading_text != text:
            continue
        used[index] = True
        return heading_id or None
    return None
