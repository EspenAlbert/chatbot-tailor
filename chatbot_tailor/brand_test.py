from __future__ import annotations

from pathlib import Path

import pytest

from chatbot_tailor import brand

HOMEPAGE = Path(__file__).parent / "testdata" / "fetch" / "homepage.html"
HTML = HOMEPAGE.read_text()


def test_parse_html_metadata() -> None:
    hints = brand.parse_html(HTML, "https://example.com/")
    assert hints.site_name == "Blinker Group"
    assert hints.language == "es"
    assert hints.description == "Suministros industriales para el automóvil."
    assert hints.theme_color == "#c8102e"


def test_title_fallback_and_default_language() -> None:
    hints = brand.parse_html("<html><head><title>  My   Site </title></head></html>", "https://example.com/")
    assert hints.site_name == "My Site"
    assert hints.language == "en"
    assert hints.description is None
    assert hints.theme_color is None


def test_stylesheets_first_two_absolute() -> None:
    hints = brand.parse_html(HTML, "https://example.com/")
    assert hints.stylesheet_urls == ["https://example.com/css/main.css", "https://example.com/css/extra.css"]


def test_favicon_is_first_svg_icon() -> None:
    hints = brand.parse_html(HTML, "https://example.com/")
    assert hints.favicon_url == "https://example.com/favicon.svg"


def test_favicon_absent_without_svg() -> None:
    hints = brand.parse_html('<link rel="icon" href="/favicon.ico">', "https://example.com/")
    assert hints.favicon_url is None


@pytest.mark.parametrize(
    ("css", "expected"),
    [
        (":root{--primary-color:#1A2B3C}", ["#1a2b3c"]),
        (":root{--brand:#FFF}", ["#fff"]),
        (":root{--accent-2:#abcd}", ["#abcd"]),
        (":root{--spacing:#fff}", []),
        (":root{--primary:hsl(1,2%,3%)}", []),
        (":root{--brand:#111;--brand-alt:#222}", ["#111", "#222"]),
        (":root{--primary:#0f62fe;--primary:#0f62fe}", ["#0f62fe", "#0f62fe"]),
    ],
)
def test_hex_colors(css: str, expected: list[str]) -> None:
    assert brand.hex_colors(css) == expected


def test_build_brand_merges_inline_and_stylesheet() -> None:
    hints = brand.parse_html(HTML, "https://example.com/")
    result = brand.build_brand(hints, [":root{--primary:#0f62fe}"], "brand/favicon.svg")
    assert result.css_colors == ["#1a2b3c", "#fff", "#abcd", "#0f62fe"]
    assert result.favicon == "brand/favicon.svg"
