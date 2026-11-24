"""Brand hints from the start page HTML: name, language, description, colors, and favicon.

The start page is read once. `parse_html` pulls the metadata and the stylesheet/icon links
from one document; `hex_colors` reads the color custom properties; `build_brand` merges the
inline and fetched stylesheet CSS. Every field may be missing.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from model_lib import Event
from pydantic import Field

from chatbot_tailor import prose

FAVICON_PATH = "brand/favicon.svg"
MAX_STYLESHEETS = 2
COLOR_WORDS = ("primary", "brand", "accent")
_CUSTOM_PROPERTY = re.compile(r"--(?P<name>[\w-]+)\s*:\s*(?P<value>[^;}]+)")
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")


class Brand(Event):
    site_name: str | None = None
    language: str = "en"
    description: str | None = None
    theme_color: str | None = None
    css_colors: list[str] = Field(default_factory=list)
    favicon: str | None = None


class HtmlHints(Event):
    site_name: str | None = None
    language: str = "en"
    description: str | None = None
    theme_color: str | None = None
    stylesheet_urls: list[str] = Field(default_factory=list)
    favicon_url: str | None = None
    inline_css: str = ""


class _BrandScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.lang: str | None = None
        self.meta: dict[str, str] = {}
        self.stylesheets: list[str] = []
        self.icons: list[str] = []
        self.styles: list[str] = []
        self._in_title = False
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        if tag == "html" and found.get("lang"):
            self.lang = found["lang"]
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self._meta(found)
        elif tag == "link":
            self._link(found)
        elif tag == "style":
            self._in_style = True

    def _meta(self, found: dict[str, str | None]) -> None:
        key = (found.get("name") or found.get("property") or "").strip().lower()
        content = found.get("content")
        if key and content is not None and key not in self.meta:
            self.meta[key] = content.strip()

    def _link(self, found: dict[str, str | None]) -> None:
        href = found.get("href")
        if not href:
            return
        rels = (found.get("rel") or "").lower().split()
        if "stylesheet" in rels:
            self.stylesheets.append(href)
        elif "icon" in rels:
            self.icons.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_style:
            self.styles.append(data)


def parse_html(html: str, page: str) -> HtmlHints:
    scan = _BrandScan()
    scan.feed(html)
    scan.close()
    title = prose.collapse(scan.title) if scan.title else ""
    stylesheets = [urljoin(page, href) for href in scan.stylesheets[:MAX_STYLESHEETS]]
    favicon = next(
        (urljoin(page, href) for href in scan.icons if urlsplit(href).path.lower().endswith(".svg")),
        None,
    )
    return HtmlHints(
        site_name=scan.meta.get("og:site_name") or title or None,
        language=scan.lang or "en",
        description=scan.meta.get("description"),
        theme_color=scan.meta.get("theme-color"),
        stylesheet_urls=stylesheets,
        favicon_url=favicon,
        inline_css="\n".join(scan.styles),
    )


def hex_colors(css: str) -> list[str]:
    found: list[str] = []
    for match in _CUSTOM_PROPERTY.finditer(css):
        if not any(word in match.group("name").lower() for word in COLOR_WORDS):
            continue
        found.extend(color.group(0).lower() for color in _HEX.finditer(match.group("value")))
    return found


def build_brand(hints: HtmlHints, stylesheet_css: list[str], favicon: str | None) -> Brand:
    css = "\n".join([hints.inline_css, *stylesheet_css])
    return Brand(
        site_name=hints.site_name,
        language=hints.language,
        description=hints.description,
        theme_color=hints.theme_color,
        css_colors=hex_colors(css),
        favicon=favicon,
    )
