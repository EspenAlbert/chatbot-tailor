from __future__ import annotations

from chatbot_tailor import sitemaps

_URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>
"""

_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""


def test_urlset_locs() -> None:
    parsed = sitemaps.parse(_URLSET)
    assert parsed.locs == ("https://example.com/a", "https://example.com/b")
    assert parsed.is_index is False


def test_sitemapindex_locs() -> None:
    parsed = sitemaps.parse(_INDEX)
    assert parsed.locs == ("https://example.com/sitemap-pages.xml",)
    assert parsed.is_index is True


def test_malformed_xml_is_empty() -> None:
    parsed = sitemaps.parse("<not xml")
    assert parsed.locs == ()
    assert parsed.is_index is False
