from __future__ import annotations

from chatbot_tailor import links

_PAGE = "https://example.com/es-es/"


def test_same_origin_links_resolves_and_filters() -> None:
    html = (
        '<a href="/a">rel</a>'
        '<a href="b">rel2</a>'
        '<a href="https://example.com/c#x">same</a>'
        '<a href="https://other.com/d">ext</a>'
        '<a href="mailto:x@example.com">mail</a>'
        '<a href="javascript:void(0)">js</a>'
    )
    assert links.same_origin_links(html, _PAGE) == [
        "https://example.com/a",
        "https://example.com/es-es/b",
        "https://example.com/c#x",
    ]


def test_anchor_without_href_is_ignored() -> None:
    assert links.same_origin_links('<a name="x">t</a><a href="">e</a>', _PAGE) == []
