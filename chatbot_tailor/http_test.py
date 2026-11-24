from __future__ import annotations

import httpx

from chatbot_tailor import http


def _response(status: int, body: bytes = b"body") -> httpx.Response:
    return httpx.Response(status, content=body)


def test_get_text_ok() -> None:
    assert http.get_text(lambda _url: _response(200, b"hello"), "https://example.com/") == "hello"


def test_get_text_non_200_is_none() -> None:
    assert http.get_text(lambda _url: _response(404), "https://example.com/") is None


def test_get_bytes_ok() -> None:
    assert http.get_bytes(lambda _url: _response(200, b"\x00\x01"), "https://example.com/") == b"\x00\x01"


def test_transport_error_is_none() -> None:
    def boom(_url: str) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert http.get_text(boom, "https://example.com/") is None
    assert http.get_bytes(boom, "https://example.com/") is None
