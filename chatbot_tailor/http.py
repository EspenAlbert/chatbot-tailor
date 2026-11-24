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
