from __future__ import annotations

from chatbot_tailor import robots

_ROBOTS = """User-agent: *
Disallow: /admin/
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap/
"""


def test_sitemaps_surfaced() -> None:
    rules = robots.parse(_ROBOTS)
    assert robots.sitemaps(rules) == ("https://example.com/sitemap.xml", "https://example.com/sitemap/")


def test_disallow_blocks_and_allows() -> None:
    rules = robots.parse(_ROBOTS)
    assert not robots.allows(rules, "https://example.com/admin/x")
    assert robots.allows(rules, "https://example.com/a")


def test_missing_robots_allows_all() -> None:
    rules = robots.parse(None)
    assert robots.sitemaps(rules) == ()
    assert robots.allows(rules, "https://example.com/anything")
