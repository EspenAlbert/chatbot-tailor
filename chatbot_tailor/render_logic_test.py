"""Render a checked site directory into a Terraform directory."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from model_lib import dump, parse

from chatbot_tailor import check_logic, render_logic

TEMPLATES = Path(__file__).parent / "templates" / "aws_chatbot"
FIXTURE = Path(__file__).parent / "testdata" / "check"


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "site"
    shutil.copytree(FIXTURE, directory)
    monkeypatch.setenv("PATH", str(tmp_path / "no-terraform"))
    return directory


def _write_tailor(directory: Path, **changes: object) -> None:
    fields = parse.parse_dict(directory / check_logic.TAILOR_FILE)
    fields.update(changes)
    (directory / check_logic.TAILOR_FILE).write_text(dump.dump_as_str(fields, "yaml"))


def _out(result: render_logic.RenderResult) -> Path:
    assert result.out_dir is not None
    return result.out_dir


def _fake_terraform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int = 0) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "terraform.log"
    script = bin_dir / "terraform"
    script.write_text('#!/bin/sh\necho "$@" >> "$LOG"\nexit ${FAKE_TERRAFORM_EXIT:-0}\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("LOG", str(log))
    monkeypatch.setenv("FAKE_TERRAFORM_EXIT", str(exit_code))
    return log


def test_hsl_channels_matches_module_greens() -> None:
    assert render_logic.hsl_channels("#00684a") == "162.7 100% 20.4%"
    assert render_logic.hsl_channels("#00ed64") == "145.3 100% 46.5%"


def test_hsl_channels_gray() -> None:
    assert render_logic.hsl_channels("#808080") == "0 0% 50.2%"


def test_raise_lightness_reaches_contrast() -> None:
    raised = render_logic.raise_lightness("#1a2b3c", render_logic.DARK_BACKGROUND)
    assert check_logic.contrast_ratio(raised, render_logic.DARK_BACKGROUND) >= check_logic.MIN_CONTRAST
    assert raised != "#1a2b3c"
    assert render_logic._hsl(raised)[2] >= render_logic._hsl("#1a2b3c")[2]


def test_raise_lightness_keeps_passing_color() -> None:
    assert render_logic.raise_lightness("#ffffff", render_logic.DARK_BACKGROUND) == "#ffffff"


def test_theme_light_and_dark_placeholders() -> None:
    theme = render_logic.render_theme("#1a2b3c")
    assert "162.7 100% 20.4%" not in theme
    assert "145.3 100% 46.5%" not in theme
    assert "__PRIMARY_LIGHT__" not in theme
    assert "__PRIMARY_DARK__" not in theme
    assert f"--primary: {render_logic.hsl_channels('#1a2b3c')};" in theme


def test_templates_name_commit() -> None:
    assert "b8f3217" in (TEMPLATES / "config.toml").read_text()
    assert "b8f3217" in (TEMPLATES / "theme.css").read_text()


def test_check_failure_stops_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    fields = parse.parse_dict(directory / check_logic.TAILOR_FILE)
    fields["app_name"] = "Bad Name"
    (directory / check_logic.TAILOR_FILE).write_text(dump.dump_as_str(fields, "yaml"))
    result = render_logic.render(directory)
    assert result.exit_code == 1
    assert result.out_dir is None
    assert "app_name: app-name" in result.failures
    assert not (directory / "out").exists()


def test_main_tf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    assert result.exit_code == 0
    assert result.out_dir == directory / "out" / "blinker"
    text = (_out(result) / "main.tf").read_text()
    assert 'source = "terraform-mongodbatlas-modules/aws-chatbot/mongodbatlas"' in text
    module_block = text.split('module "chatbot" {', 1)[1].split("\n}", 1)[0]
    assert "version" not in module_block
    assert 'app_name = "blinker"' in module_block
    for query in parse.parse_dict(directory / check_logic.TAILOR_FILE)["queries"]:
        assert query["label"] in module_block
        assert query["message"] in module_block
    assert "system_prompt = <<-EOT" in module_block
    prompt = parse.parse_dict(directory / check_logic.TAILOR_FILE)["system_prompt"]
    for line in prompt.splitlines():
        assert f"    {line}" in module_block
    assert '"${path.module}/docs"' in module_block
    assert "skip_repo_docs = true" in module_block
    assert '"${path.module}/assets"' in module_block
    assert 'output "https_url"' in text
    assert "module.chatbot.https_url" in text
    assert "module.chatbot.chatbot_login_password" in text


def test_queries_omit_page_and_quote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    text = (_out(result) / "main.tf").read_text()
    module_block = text.split('module "chatbot" {', 1)[1].split("\n}", 1)[0]
    assert "page =" not in module_block
    assert "quote =" not in module_block


def test_docs_copied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    pages = directory / check_logic.PAGES_DIR
    docs = _out(result) / render_logic.DOCS_DIR
    assert sorted(path.name for path in docs.glob("*.md")) == sorted(path.name for path in pages.glob("*.md"))
    for page in pages.glob("*.md"):
        assert (docs / page.name).read_text() == page.read_text()


def test_previous_render_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    stale = directory / "out" / "blinker" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale")
    result = render_logic.render(directory)
    assert not stale.exists()
    assert (_out(result) / "main.tf").is_file()


def test_config_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    config = (_out(result) / "assets" / ".chainlit" / "config.toml").read_text()
    assert 'name = "Blinker Group"' in config
    assert 'description = "Asistente de suministros industriales."' in config
    assert 'custom_css = "/public/theme.css"' in config
    assert 'custom_js = "/public/command-buttons.js"' in config
    assert 'language = "en-US"' in config


def test_config_escapes_ui_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    _write_tailor(directory, ui_name='Blinker "Group"')
    result = render_logic.render(directory)
    config = (_out(result) / "assets" / ".chainlit" / "config.toml").read_text()
    assert 'name = "Blinker \\"Group\\""' in config


def test_chainlit_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    stamp = datetime(2026, 11, 20, 12, 0, tzinfo=UTC).timestamp()
    expected_date = datetime.fromtimestamp(stamp, tz=UTC).astimezone().date().isoformat()
    pages = sorted((directory / check_logic.PAGES_DIR).glob("*.md"))
    for page in pages:
        os.utime(page, (stamp, stamp))
    result = render_logic.render(directory)
    text = (_out(result) / "assets" / "chainlit.md").read_text()
    assert "# Blinker Group" in text
    assert f"3 pages fetched on {expected_date}." in text
    for page in pages:
        assert f"- {page.read_text().splitlines()[0]}" in text


def test_theme_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    theme = (_out(result) / "assets" / "public" / "theme.css").read_text()
    assert "__PRIMARY_LIGHT__" not in theme
    assert "__PRIMARY_DARK__" not in theme
    assert f"--primary: {render_logic.hsl_channels('#1a2b3c')};" in theme


def test_favicon_copied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    favicon = directory / "brand" / "favicon.svg"
    favicon.parent.mkdir()
    favicon.write_text('<svg xmlns="http://www.w3.org/2000/svg" />')
    result = render_logic.render(directory)
    copied = _out(result) / "assets" / "public" / "favicon.svg"
    assert copied.read_bytes() == favicon.read_bytes()


def test_favicon_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    assert not (_out(result) / "assets" / "public" / "favicon.svg").exists()


def test_assets_overlay_only_touches_brand_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    assets = _out(result) / "assets"
    files = sorted(str(path.relative_to(assets)) for path in assets.rglob("*") if path.is_file())
    assert files == [".chainlit/config.toml", "chainlit.md", "public/theme.css"]


def test_terraform_runs_three_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    log = _fake_terraform(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    assert result.exit_code == 0
    assert log.read_text().splitlines() == ["fmt", "init -backend=false", "validate"]


def test_terraform_failure_fails_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    _fake_terraform(tmp_path, monkeypatch, exit_code=1)
    result = render_logic.render(directory)
    assert result.exit_code == 1
    assert result.out_dir is not None
    assert "terraform fmt failed" in result.detail
    assert (result.out_dir / "main.tf").is_file()


def test_no_terraform_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _fixture(tmp_path, monkeypatch)
    result = render_logic.render(directory)
    assert result.exit_code == 0
    assert result.detail == ""
