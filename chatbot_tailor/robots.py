"""robots.txt: allowed paths and sitemap URLs."""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

AGENT = "*"


def parse(text: str | None) -> RobotFileParser:
    parser = RobotFileParser()
    # An unparsed parser denies every URL, so always parse (empty when the file is missing).
    parser.parse((text or "").splitlines(keepends=True))
    return parser


def sitemaps(parser: RobotFileParser) -> tuple[str, ...]:
    return tuple(parser.site_maps() or ())


def allows(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(AGENT, url)
