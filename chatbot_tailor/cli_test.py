from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import chatbot_tailor.cli as cli_module
from chatbot_tailor import check_logic, discover_logic, fetch_logic, render_logic
from chatbot_tailor.cli import app
from chatbot_tailor.discover_logic import DiscoverResult, Hint
from chatbot_tailor.fetch_logic import FetchResult
from chatbot_tailor.render_logic import RenderResult

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


def test_check_prints_failures_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    result = check_logic.CheckResult(failures=[check_logic.CheckFailure(field="app_name", rule="app-name")])
    monkeypatch.setattr(check_logic, "check", lambda directory: result)
    invoked = runner.invoke(app, ["check", str(tmp_path)])
    assert invoked.exit_code == 1
    assert "app_name: app-name" in invoked.output + caplog.text


def test_check_clean_exits_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(check_logic, "check", lambda directory: check_logic.CheckResult())
    invoked = runner.invoke(app, ["check", str(tmp_path)])
    assert invoked.exit_code == 0


def test_check_without_directory_exits_two() -> None:
    invoked = runner.invoke(app, ["check"])
    assert invoked.exit_code == 2


def test_render_prints_out_dir_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    out_dir = tmp_path / "out" / "blinker"
    monkeypatch.setattr(render_logic, "render", lambda directory: RenderResult(exit_code=0, out_dir=out_dir))
    invoked = runner.invoke(app, ["render", str(tmp_path)])
    assert invoked.exit_code == 0
    assert str(out_dir) in invoked.output + caplog.text


def test_render_prints_check_failures_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.INFO)
    result = RenderResult(exit_code=1, failures=["app_name: app-name"], detail="check failed")
    monkeypatch.setattr(render_logic, "render", lambda directory: result)
    invoked = runner.invoke(app, ["render", str(tmp_path)])
    assert invoked.exit_code == 1
    text = invoked.output + caplog.text
    assert "app_name: app-name" in text
    assert "check failed" in text


def test_render_prints_terraform_detail_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    caplog.set_level(logging.ERROR)
    result = RenderResult(exit_code=1, out_dir=tmp_path, detail="terraform validate failed (1): bad")
    monkeypatch.setattr(render_logic, "render", lambda directory: result)
    invoked = runner.invoke(app, ["render", str(tmp_path)])
    assert invoked.exit_code == 1
    assert "terraform validate failed" in invoked.output + caplog.text


def test_render_without_directory_exits_two() -> None:
    invoked = runner.invoke(app, ["render"])
    assert invoked.exit_code == 2
