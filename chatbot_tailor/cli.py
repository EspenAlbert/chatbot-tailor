"""Typer registration for chatbot-tailor."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from pydantic import ValidationError

from chatbot_tailor import discover_logic, fetch_logic
from chatbot_tailor.discover_logic import DiscoverInput, Hint

logger = logging.getLogger(__name__)

app = typer.Typer(name="chatbot-tailor", no_args_is_help=True)


@app.callback()
def main(
    log_level: str = typer.Option("INFO", help="Logging level: INFO, WARNING, ERROR, CRITICAL."),
) -> None:
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO), format="%(message)s")


@app.command()
def discover(url: str = typer.Option(..., "--url", help="Start page URL.")) -> None:
    try:
        data = DiscoverInput(url=url, workspace_root=Path.cwd())
    except ValidationError as exc:
        error = exc.errors()[0]
        detail = error.get("ctx", {}).get("error", error["msg"])
        logger.error(detail)
        raise typer.Exit(2) from exc
    result = discover_logic.discover(data)
    logger.info(str(result.path))
    for hint in (Hint.KEEP, Hint.MAYBE, Hint.DROP):
        logger.info(f"{hint}: {result.counts.get(hint, 0)}")


@app.command()
def fetch(directory: Path = typer.Argument(..., help="Directory with pages.yaml and candidates.yaml.")) -> None:
    result = fetch_logic.fetch(directory)
    for line in result.skipped:
        logger.warning(line)
    for slug in result.written:
        logger.info(slug)
    if result.brand_path:
        logger.info(str(result.brand_path))
    logger.info(f"pages: {len(result.written)}")
    if result.exit_code != 0:
        logger.error(result.detail)
        raise typer.Exit(result.exit_code)


def typer_main() -> None:
    app()
