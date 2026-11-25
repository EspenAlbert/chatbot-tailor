"""Check tailor.yaml against the fetched pages."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from model_lib import dump, parse

from chatbot_tailor import check_logic

FIXTURE = Path(__file__).parent / "testdata" / "check"


def copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "site"
    shutil.copytree(FIXTURE, dest)
    return dest


def load_tailor(directory: Path) -> dict:
    return parse.parse_dict(directory / check_logic.TAILOR_FILE)


def write_tailor(directory: Path, fields: dict) -> None:
    (directory / check_logic.TAILOR_FILE).write_text(dump.dump_as_str(fields, "yaml"))


def lines_after(directory: Path, **changes: object) -> list[str]:
    fields = load_tailor(directory)
    fields.update(changes)
    write_tailor(directory, fields)
    return check_logic.check(directory).lines


def lines_with_query(directory: Path, index: int, **changes: object) -> list[str]:
    fields = load_tailor(directory)
    fields["queries"][index - 1].update(changes)
    write_tailor(directory, fields)
    return check_logic.check(directory).lines


def test_valid_fixture() -> None:
    assert check_logic.check(FIXTURE).lines == []


def test_missing_tailor_file(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    (directory / check_logic.TAILOR_FILE).unlink()
    assert check_logic.check(directory).lines == [f"{check_logic.TAILOR_FILE}: {check_logic.RULE_MISSING_FILE}"]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"app_name": "Bad Name"}, "app_name: app-name"),
        ({"app_name": "a" * 24}, "app_name: app-name"),
        ({"ui_name": ""}, "ui_name: ui-name-empty"),
        ({"ui_description": ""}, "ui_description: ui-description-empty"),
        ({"language": ""}, "language: language-empty"),
        ({"language": "fr"}, "language: language-mismatch"),
        ({"primary_color": "red"}, "primary_color: primary-color-format"),
        ({"primary_color": "#eeeeee"}, "primary_color: primary-color-contrast"),
        ({"queries": []}, "queries: queries-count"),
        ({"queries": [{"label": "x"}] * 3}, "queries: queries-count"),
    ],
)
def test_scalar_failures(tmp_path: Path, changes: dict, expected: str) -> None:
    directory = copy_fixture(tmp_path)
    assert expected in lines_after(directory, **changes)


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("", "system_prompt: system-prompt-empty"),
        ("Eres un asistente útil. Habla en español.", "system_prompt: system-prompt-company"),
        ("Eres el asistente de Blinker Group.", "system_prompt: system-prompt-language"),
    ],
)
def test_system_prompt_failures(tmp_path: Path, prompt: str, expected: str) -> None:
    directory = copy_fixture(tmp_path)
    assert expected in lines_after(directory, system_prompt=prompt)


def test_label_long(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    assert "queries[1].label: label-long" in lines_with_query(directory, 1, label="x" * 31)


def test_label_duplicate(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    fields = load_tailor(directory)
    fields["queries"][1]["label"] = fields["queries"][0]["label"]
    write_tailor(directory, fields)
    lines = check_logic.check(directory).lines
    assert "queries[1].label: label-duplicate" in lines
    assert "queries[2].label: label-duplicate" in lines


def test_page_missing(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    assert "queries[1].page: page-missing" in lines_with_query(directory, 1, page="nope")


def test_page_traversal_rejected(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    assert "queries[1].page: page-missing" in lines_with_query(directory, 1, page="../empresa")


def test_quote_short(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    assert "queries[1].quote: quote-short" in lines_with_query(directory, 1, quote="solo cinco palabras cortas aquí")


def test_quote_not_in_page(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    quote = "Una oración completamente inventada que no aparece en la página origen."
    assert "queries[1].quote: quote-not-in-page" in lines_with_query(directory, 1, quote=quote)


def test_quote_is_case_sensitive(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    quote = "1hourtec es el servicio de entrega urgente que lleva repuestos a cualquier taller en una hora."
    assert "queries[1].quote: quote-not-in-page" in lines_with_query(directory, 1, quote=quote)


def test_quote_with_newline_passes_after_collapse(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    quote = "1Hourtec es el servicio de entrega urgente\nque lleva repuestos a cualquier taller en una hora."
    assert lines_with_query(directory, 1, quote=quote) == []


def test_contrast_ratio_bounds() -> None:
    assert check_logic.contrast_ratio("#000000", check_logic.WHITE) == pytest.approx(21.0)
    assert check_logic.contrast_ratio(check_logic.WHITE, check_logic.WHITE) == pytest.approx(1.0)
