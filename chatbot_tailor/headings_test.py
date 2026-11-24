from __future__ import annotations

from chatbot_tailor import headings

_HTML = """
<html><body>
<h1>Why I Enforce 100% Test Coverage</h1>
<h2 id="95-seems-good-right">95% seems good, right?</h2>
<h2>No id here</h2>
</body></html>
"""

_MARKDOWN = """# Why I Enforce 100% Test Coverage

## 95% seems good, right?

## No id here
"""


def test_html_id_on_coverage_heading() -> None:
    marked = headings.apply_html_ids(_MARKDOWN, _HTML)
    assert "## 95% seems good, right? {#95-seems-good-right}" in marked
    assert "{#" not in marked.splitlines()[0]
    unmarked = next(line for line in marked.splitlines() if line.startswith("## No id"))
    assert "{#" not in unmarked


def test_fenced_heading_is_not_marked() -> None:
    markdown = "```\n## 95% seems good, right?\n```\n\n## 95% seems good, right?\n"
    html = '<h2 id="95-seems-good-right">95% seems good, right?</h2>'
    marked = headings.apply_html_ids(markdown, html)
    assert "```\n## 95% seems good, right?\n```" in marked
    assert "## 95% seems good, right? {#95-seems-good-right}" in marked


def test_has_heading_ignores_marker() -> None:
    assert headings.has_heading("## Title {#title}\n", "Title")
    assert not headings.has_heading("Title\n", "Title")
