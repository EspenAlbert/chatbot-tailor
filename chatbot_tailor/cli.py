"""Typer registration for chatbot-tailor."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from pydantic import ValidationError

from chatbot_tailor import discover_logic
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


def typer_main() -> None:
    app()
