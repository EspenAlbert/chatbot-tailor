"""Sitemap and sitemap-index loc extraction."""

from __future__ import annotations

from xml.etree import ElementTree

from model_lib import Event
from pydantic import Field

_INDEX = "sitemapindex"
_URLSET = "urlset"


class Sitemap(Event):
    locs: tuple[str, ...] = Field(default_factory=tuple)
    is_index: bool = False


def parse(xml_text: str) -> Sitemap:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return Sitemap()
    name = _local_name(root.tag)
    if name not in {_INDEX, _URLSET}:
        return Sitemap()
    locs = tuple(
        text for element in root.iter() if _local_name(element.tag) == "loc" and (text := (element.text or "").strip())
    )
    return Sitemap(locs=locs, is_index=name == _INDEX)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
