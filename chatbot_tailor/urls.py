"""Page URL and slug.

Copied from py-play anki_nuggets/urls.py at 2d04330, without the GitHub and gist mapping.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import urldefrag, urlsplit, urlunsplit


def page_url(url: str) -> str:
    return urldefrag(url).url


def slug_from_url(url: str) -> str:
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if not segments:
        return ""
    return PurePosixPath(segments[-1]).stem.lower()


def strip_query_fragment(url: str) -> str:
    split = urlsplit(url)
    return urlunsplit((split.scheme, split.netloc, split.path, "", ""))


def origin(url: str) -> str:
    split = urlsplit(url)
    return f"{split.scheme}://{split.netloc}"


def same_origin(url: str, base: str) -> bool:
    return origin(url).lower() == origin(base).lower()


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


def candidates_path(workspace_root: Path, day: date, url: str) -> Path:
    host = (urlsplit(url).hostname or "").lower()
    return workspace_root / "cache" / "chatbot-tailor" / f"{day:%Y-%m-%d}" / host / "candidates.yaml"
