from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import chatbot_tailor.cli as cli_module
from chatbot_tailor import discover_logic, fetch_logic
from chatbot_tailor.cli import app
from chatbot_tailor.discover_logic import DiscoverResult, Hint
from chatbot_tailor.fetch_logic import FetchResult

runner = CliRunner()


def test_discover_prints_path_and_counts(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    def fake(_data: discover_logic.DiscoverInput) -> DiscoverResult:
        return DiscoverResult(path=Path("/tmp/candidates.yaml"), counts={Hint.KEEP: 2, Hint.MAYBE: 1, Hint.DROP: 3})

    monkeypatch.setattr(discover_logic, "discover", fake)
    result = runner.invoke(app, ["discover", "--url", "https://example.com/"])
    assert result.exit_code == 0
    text = result.output + caplog.text
    assert "/tmp/candidates.yaml" in text
    assert "keep: 2" in text
    assert "maybe: 1" in text
    assert "drop: 3" in text


def test_discover_rejects_non_http(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    result = runner.invoke(app, ["discover", "--url", "ftp://example.com"])
    assert result.exit_code == 2
    assert "url must be http or https" in result.output + caplog.text


def test_typer_main_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app_mock = MagicMock()
    monkeypatch.setattr(cli_module, "app", app_mock)
    cli_module.typer_main()
    app_mock.assert_called_once()


def test_fetch_logs_skips_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    result = FetchResult(
        exit_code=0,
        written=["product"],
        skipped=["https://example.com/x: HTTP 404"],
        brand_path=tmp_path / "brand.yaml",
    )
    monkeypatch.setattr(fetch_logic, "fetch", lambda directory: result)
    invoked = runner.invoke(app, ["fetch", str(tmp_path)])
    assert invoked.exit_code == 0
    text = invoked.output + caplog.text
    assert "https://example.com/x: HTTP 404" in text
    assert "brand.yaml" in text
    assert "pages: 1" in text


def test_fetch_zero_survivors_exits_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    result = FetchResult(exit_code=1, skipped=["https://example.com/x: empty extract"], detail="no pages survived")
    monkeypatch.setattr(fetch_logic, "fetch", lambda directory: result)
    invoked = runner.invoke(app, ["fetch", str(tmp_path)])
    assert invoked.exit_code == 1
    assert "no pages survived" in invoked.output + caplog.text


def test_fetch_without_directory_exits_two() -> None:
    invoked = runner.invoke(app, ["fetch"])
    assert invoked.exit_code == 2
