from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from model_lib import dump, parse

from chatbot_tailor import fetch_logic, fetch_page
from chatbot_tailor.fetch_logic import EXIT_EMPTY, EXIT_INPUT
from chatbot_tailor.http import Get

HOMEPAGE = Path(__file__).parent / "testdata" / "fetch" / "homepage.html"
START = "https://example.com/"
PRODUCT = "https://example.com/product/"
FAVICON_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
_PAGE_HTML = '<html><body><h2 id="why">Why</h2><p>Body.</p></body></html>'
_LONG = "## Why\n\n" + "word " * 200


def _response(body: str | bytes, status: int = 200, content_type: str = "text/html") -> httpx.Response:
    data = body.encode() if isinstance(body, str) else body
    return httpx.Response(status, content=data, headers={"content-type": content_type})


def _stub(routes: dict[str, httpx.Response], requested: list[str] | None = None) -> Get:
    def get(url: str) -> httpx.Response:
        if requested is not None:
            requested.append(url)
        return routes.get(url, _response("missing", status=404))

    return get


def _write_pages(directory: Path, urls: list[str], start: str = START) -> None:
    (directory / "pages.yaml").write_text(dump.dump_as_str(urls, "yaml"))
    (directory / "candidates.yaml").write_text(dump.dump_as_str([{"url": start, "path": "/", "hint": "keep"}], "yaml"))


@pytest.fixture
def long_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_page.trafilatura, "extract", lambda *_a, **_k: _LONG)
    monkeypatch.setattr(fetch_page.trafilatura, "extract_metadata", lambda *_a, **_k: SimpleNamespace(title=""))


def _brand_routes() -> dict[str, httpx.Response]:
    return {
        START: _response(HOMEPAGE.read_text()),
        "https://example.com/css/main.css": _response(":root{--primary:#0f62fe}", content_type="text/css"),
        "https://example.com/css/extra.css": _response(":root{--brand-accent:#0043ce}", content_type="text/css"),
        "https://example.com/favicon.svg": _response(FAVICON_SVG, content_type="image/svg+xml"),
        PRODUCT: _response(_PAGE_HTML),
    }


def test_writes_page_with_url_first_line_and_marker(tmp_path: Path, long_extract: None) -> None:
    _write_pages(tmp_path, [PRODUCT])
    result = fetch_logic.fetch(tmp_path, get=_stub(_brand_routes()))
    assert result.exit_code == 0
    assert result.written == ["product"]
    lines = (tmp_path / "pages" / "product.md").read_text().splitlines()
    assert lines[0] == PRODUCT
    assert "## Why {#why}" in "\n".join(lines)


def test_brand_from_start_page(tmp_path: Path, long_extract: None) -> None:
    _write_pages(tmp_path, [PRODUCT])
    requested: list[str] = []
    result = fetch_logic.fetch(tmp_path, get=_stub(_brand_routes(), requested))
    assert result.brand_path == tmp_path / "brand.yaml"
    loaded = parse.parse_dict(tmp_path / "brand.yaml")
    assert loaded["site_name"] == "Blinker Group"
    assert loaded["language"] == "es"
    assert loaded["description"] == "Suministros industriales para el automóvil."
    assert loaded["theme_color"] == "#c8102e"
    assert loaded["css_colors"] == ["#1a2b3c", "#fff", "#abcd", "#0f62fe", "#0043ce"]
    assert loaded["favicon"] == "brand/favicon.svg"
    assert (tmp_path / "brand" / "favicon.svg").read_bytes() == FAVICON_SVG
    assert "https://example.com/css/third.css" not in requested


def test_brand_defaults_when_start_page_missing(tmp_path: Path, long_extract: None) -> None:
    _write_pages(tmp_path, [PRODUCT])
    result = fetch_logic.fetch(tmp_path, get=_stub({PRODUCT: _response(_PAGE_HTML)}))
    assert result.exit_code == 0
    loaded = parse.parse_dict(tmp_path / "brand.yaml")
    assert loaded["language"] == "en"
    assert loaded["css_colors"] == []
    assert "favicon" not in loaded
    assert not (tmp_path / "brand").exists()


def test_non_200_skipped(tmp_path: Path, long_extract: None) -> None:
    _write_pages(tmp_path, ["https://example.com/gone/"])
    result = fetch_logic.fetch(tmp_path, get=_stub({}))
    assert result.skipped == ["https://example.com/gone/: HTTP 404"]
    assert result.exit_code == EXIT_EMPTY
    assert not (tmp_path / "pages").exists()


def test_empty_extract_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_page.trafilatura, "extract", lambda *_a, **_k: None)
    _write_pages(tmp_path, [PRODUCT])
    result = fetch_logic.fetch(tmp_path, get=_stub({PRODUCT: _response("<html></html>")}))
    assert result.skipped == [f"{PRODUCT}: empty extract"]


def test_under_word_floor_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_page.trafilatura, "extract", lambda *_a, **_k: "## Why\n\nshort body.")
    monkeypatch.setattr(fetch_page.trafilatura, "extract_metadata", lambda *_a, **_k: SimpleNamespace(title=""))
    _write_pages(tmp_path, [PRODUCT])
    result = fetch_logic.fetch(tmp_path, get=_stub({PRODUCT: _response(_PAGE_HTML)}))
    assert result.skipped == [f"{PRODUCT}: under 150 words (4)"]
    assert not (tmp_path / "pages").exists()


def test_slugs_are_unique_and_root_is_index() -> None:
    urls = ["https://example.com/", "https://example.com/product/x", "https://example.com/other/x"]
    assert fetch_logic.slugs(urls) == ["index", "x", "x-2"]


def test_empty_pages_exits_empty(tmp_path: Path) -> None:
    _write_pages(tmp_path, [])
    result = fetch_logic.fetch(tmp_path, get=_stub({}))
    assert result.exit_code == EXIT_EMPTY
    assert result.detail == "no pages survived"


def test_missing_pages_exits_input(tmp_path: Path) -> None:
    result = fetch_logic.fetch(tmp_path, get=_stub({}))
    assert result.exit_code == EXIT_INPUT
    assert result.detail == "pages.yaml: missing or not a list of URLs"


def test_start_url_falls_back_to_pages(tmp_path: Path) -> None:
    (tmp_path / "pages.yaml").write_text(dump.dump_as_str([PRODUCT], "yaml"))
    assert fetch_logic.start_url(tmp_path) == PRODUCT


def test_start_url_from_candidates_first_row(tmp_path: Path) -> None:
    _write_pages(tmp_path, [PRODUCT])
    assert fetch_logic.start_url(tmp_path) == START
