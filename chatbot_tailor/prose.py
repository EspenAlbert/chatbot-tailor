"""Page prose: the text after the URL line, with heading markers removed.

Copied from py-play anki_nuggets/prose.py at 2d04330, without the byline, image, and card helpers.
"""

from __future__ import annotations

import re

_MARKER = re.compile(r"\s*\{#[^}]+\}")


def collapse(text: str) -> str:
    return " ".join(text.split())


def page_prose(source: str) -> str:
    body = "\n".join(source.splitlines()[1:])
    return _MARKER.sub("", body)


def prose_word_count(source: str) -> int:
    return len(page_prose(source).split())
