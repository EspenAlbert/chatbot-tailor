from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from chatbot_tailor import prose, urls


def test_word_count_ignores_url_and_marker() -> None:
    source = "https://example.com/a\n\n## Title {#title}\n\nhello world\n"
    assert prose.prose_word_count(source) == 4


def test_page_url_drops_fragment_keeps_query() -> None:
    assert urls.page_url("https://example.com/a/#usage") == "https://example.com/a/"
    assert urls.page_url("https://example.com/a?tab=1") == "https://example.com/a?tab=1"


@pytest.mark.parametrize(
    ("url", "slug"),
    [
        ("https://marcelotryle.com/blog/100-percent-coverage/", "100-percent-coverage"),
        ("https://example.com/a/file.html", "file"),
        ("https://blinkergroup.com/", ""),
    ],
)
def test_slug(url: str, slug: str) -> None:
    assert urls.slug_from_url(url) == slug


def test_strip_query_fragment_removes_query_and_fragment() -> None:
    assert urls.strip_query_fragment("https://example.com/a?x=1#y") == "https://example.com/a"
    assert urls.strip_query_fragment("https://example.com/a/") == "https://example.com/a/"


def test_origin_and_same_origin() -> None:
    assert urls.origin("https://example.com/a?b=1") == "https://example.com"
    assert urls.same_origin("https://example.com/a", "https://EXAMPLE.com/b")
    assert not urls.same_origin("https://example.com/a", "https://other.com/a")
    assert not urls.same_origin("https://example.com/a", "http://example.com/a")


def test_path_of() -> None:
    assert urls.path_of("https://example.com/a/b?c=1") == "/a/b"
    assert urls.path_of("https://example.com") == "/"


def test_candidates_path_uses_date_and_host(tmp_path: Path) -> None:
    path = urls.candidates_path(tmp_path, date(2026, 11, 24), "https://WWW.BlinkerGroup.com/es-es/")
    assert path == tmp_path / "cache" / "chatbot-tailor" / "2026-11-24" / "www.blinkergroup.com" / "candidates.yaml"
