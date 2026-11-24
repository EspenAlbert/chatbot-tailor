from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

from chatbot_tailor import discover_logic
from chatbot_tailor.discover_logic import DiscoverInput, DiscoverResult, Hint
from chatbot_tailor.http import Get

FIXTURES = Path(__file__).parent / "testdata" / "discover"
START = "https://example.com/"
DAY = date(2026, 11, 24)
_HINTS = ("keep", "maybe", "drop")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _get(fixtures: dict[str, str]) -> Get:
    def get(url: str) -> httpx.Response:
        if body := fixtures.get(url):
            return httpx.Response(200, text=body)
        return httpx.Response(404, text="")

    return get


def _example_fixtures() -> dict[str, str]:
    return {
        "https://example.com/llms.txt": _fixture("llms.txt"),
        "https://example.com/robots.txt": _fixture("robots.txt"),
        "https://example.com/sitemap.xml": _fixture("sitemap.xml"),
        "https://example.com/sitemap-pages.xml": _fixture("sitemap-pages.xml"),
        "https://example.com/": _fixture("homepage.html"),
    }


def _run(tmp_path: Path, fixtures: dict[str, str] | None = None) -> tuple[DiscoverResult, list[dict]]:
    result = discover_logic.discover(
        DiscoverInput(url=START, workspace_root=tmp_path, today=DAY), get=_get(fixtures or _example_fixtures())
    )
    return result, yaml.safe_load(result.path.read_text())


def test_discover_writes_path_with_hints(tmp_path: Path) -> None:
    result, rows = _run(tmp_path)
    expected = tmp_path / "cache" / "chatbot-tailor" / "2026-11-24" / "example.com" / "candidates.yaml"
    assert result.path == expected
    assert expected.is_file()
    by_url = {row["url"]: row["hint"] for row in rows}
    assert by_url["https://example.com/"] == "keep"
    assert by_url["https://example.com/about"] == "keep"
    assert by_url["https://example.com/careers"] == "drop"
    assert "https://example.com/private/secret" not in by_url
    assert all(row["url"].startswith("https://example.com") for row in rows)
    hints = [row["hint"] for row in rows]
    assert hints == sorted(hints, key=_HINTS.index)
    counts = {hint: hints.count(hint) for hint in _HINTS}
    assert result.counts == counts


def test_llms_urls_are_kept(tmp_path: Path) -> None:
    _result, rows = _run(tmp_path)
    by_url = {row["url"]: row["hint"] for row in rows}
    assert by_url["https://example.com/product"] == "keep"
    assert by_url["https://example.com/pricing"] == "keep"


def test_sitemap_index_locs_added(tmp_path: Path) -> None:
    _result, rows = _run(tmp_path)
    urls = {row["url"] for row in rows}
    assert "https://example.com/product/a" in urls
    assert "https://example.com/careers" in urls


def test_homepage_anchors_added(tmp_path: Path) -> None:
    _result, rows = _run(tmp_path)
    urls = {row["url"] for row in rows}
    assert "https://example.com/about" in urls
    assert "https://example.com/solutions" in urls
    assert "https://other.com/x" not in urls


def test_robots_disallow_drops_paths(tmp_path: Path) -> None:
    _result, rows = _run(tmp_path)
    assert "https://example.com/private/secret" not in {row["url"] for row in rows}


def test_normalizes_query_fragment_and_dedups(tmp_path: Path) -> None:
    _result, rows = _run(tmp_path)
    urls = [row["url"] for row in rows]
    assert "https://example.com/product/a" in urls
    assert urls.count("https://example.com/product/a") == 1


def test_cap_and_order_keep_first(tmp_path: Path) -> None:
    anchors = "".join(f'<a href="/p{i}">x</a>' for i in range(320))
    fixtures = {"https://example.com/": f"<html>{anchors}</html>"}
    _result, rows = _run(tmp_path, fixtures)
    assert len(rows) == discover_logic.MAX_CANDIDATES
    hints = [row["hint"] for row in rows]
    assert hints[0] == "keep"
    assert hints == sorted(hints, key=_HINTS.index)


@pytest.mark.parametrize(
    ("url", "hint"),
    [
        ("https://example.com/product", Hint.KEEP),
        ("https://example.com/pricing", Hint.KEEP),
        ("https://example.com/faq", Hint.KEEP),
        ("https://example.com/careers", Hint.DROP),
        ("https://example.com/login", Hint.DROP),
        ("https://example.com/blog/2024/01/post", Hint.DROP),
        ("https://example.com/contact", Hint.MAYBE),
        ("https://example.com/", Hint.MAYBE),
        ("https://example.com/product/terms", Hint.DROP),
        ("https://example.com/legal/support", Hint.DROP),
        ("https://example.com/blog/2024/01/our-new-product", Hint.DROP),
    ],
)
def test_classify_drop_first(url: str, hint: Hint) -> None:
    assert discover_logic.classify(url) == hint


def test_llms_urls_strips_trailing_punctuation() -> None:
    text = "See [docs](https://example.com/docs), and https://example.com/faq."
    assert discover_logic.llms_urls(text) == ["https://example.com/docs", "https://example.com/faq"]


def test_discover_input_rejects_non_http() -> None:
    with pytest.raises(ValidationError):
        DiscoverInput(url="ftp://example.com", workspace_root=Path("/tmp"))
