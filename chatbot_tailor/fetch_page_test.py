from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from chatbot_tailor import fetch_page
from chatbot_tailor.fetch_page import Page, Skipped

COVERAGE = "https://marcelotryle.com/blog/100-percent-coverage/"
_HTML = '<html><h1>Missing Title</h1><h2 id="why">Why</h2><p>Body words stay.</p></html>'


def _response(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html"})


@pytest.mark.parametrize("status", [401, 402, 403, 404, 500])
def test_non_200_is_skipped_with_status(status: int) -> None:
    result = fetch_page.fetch_page(COVERAGE, get=lambda _url: _response("no", status=status))
    assert result == Skipped(url=COVERAGE, reason=f"HTTP {status}", status=status)


def test_empty_extract_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch_page.trafilatura, "extract", lambda *_a, **_k: None)
    result = fetch_page.fetch_page(COVERAGE, get=lambda _url: _response("<html></html>"))
    assert result == Skipped(url=COVERAGE, reason="empty extract")


def test_transport_error_is_skipped() -> None:
    def get(_url: str) -> httpx.Response:
        raise httpx.ConnectError("down")

    result = fetch_page.fetch_page(COVERAGE, get=get)
    assert isinstance(result, Skipped)
    assert "down" in result.reason


def test_fragment_dropped_title_prepended_and_heading_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def extract(*_args: object, **kwargs: object) -> str:
        assert kwargs["output_format"] == "markdown"
        assert kwargs["include_comments"] is False
        return "## Why\n\nBody words stay."

    def get(url: str) -> httpx.Response:
        calls.append(url)
        return _response(_HTML)

    monkeypatch.setattr(fetch_page.trafilatura, "extract", extract)
    monkeypatch.setattr(
        fetch_page.trafilatura, "extract_metadata", lambda *_a, **_k: SimpleNamespace(title="Missing Title")
    )
    result = fetch_page.fetch_page(f"{COVERAGE}#why", get=get)
    assert calls == [COVERAGE]
    assert isinstance(result, Page)
    assert result.source.splitlines() == [COVERAGE, "# Missing Title", "", "## Why {#why}", "", "Body words stay."]
    assert result.word_count == 8
