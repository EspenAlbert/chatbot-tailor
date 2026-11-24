from __future__ import annotations

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
