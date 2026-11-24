"""HTTP GET shared by the fetch and discover commands."""

from __future__ import annotations

from collections.abc import Callable

import httpx

Get = Callable[[str], httpx.Response]


def http_get(url: str) -> httpx.Response:
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url)
        response.read()
        return response


def get_text(get: Get, url: str) -> str | None:
    response = _ok(get, url)
    return None if response is None else response.text


def get_bytes(get: Get, url: str) -> bytes | None:
    response = _ok(get, url)
    return None if response is None else response.content


def _ok(get: Get, url: str) -> httpx.Response | None:
    try:
        response = get(url)
    except (httpx.HTTPError, UnicodeError):
        return None
    return response if response.status_code == 200 else None
