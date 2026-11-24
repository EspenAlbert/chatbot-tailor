"""Page URL and slug.

Copied from py-play anki_nuggets/urls.py at 2d04330, without the GitHub and gist mapping.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import urldefrag, urlsplit


def page_url(url: str) -> str:
    return urldefrag(url).url


def slug_from_url(url: str) -> str:
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if not segments:
        return ""
    return PurePosixPath(segments[-1]).stem.lower()
