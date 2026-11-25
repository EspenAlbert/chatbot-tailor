"""Check tailor.yaml against the fetched pages and brand.yaml.

The skill writes tailor.yaml. `check` reads it as a raw mapping so each broken
field reports its own `{field}: {rule}` line, then validates the field rules,
each query's page file, the quote against that page's prose, and the primary
color's contrast against white.
"""

from __future__ import annotations

import re
from pathlib import Path

from model_lib import Event, parse
from model_lib.errors import PayloadError
from pydantic import Field

from chatbot_tailor import prose

TAILOR_FILE = "tailor.yaml"
PAGES_DIR = "pages"
BRAND_FILE = "brand.yaml"
QUERY_COUNT = 4
LABEL_MAX = 30
QUOTE_MIN_WORDS = 8
MIN_CONTRAST = 3.0
WHITE = "#ffffff"
APP_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,22}$")
PRIMARY_COLOR_PATTERN = re.compile(r"^#[0-9a-f]{6}$")
# ponytail: known non-English codes only. An unknown code or `en` skips the token
# check instead of guessing a name, so a default English prompt is never a failure.
LANGUAGE_NAMES: dict[str, tuple[str, ...]] = {
    "es": ("español", "spanish"),
    "fr": ("français", "french"),
    "de": ("deutsch", "german"),
    "pt": ("português", "portuguese"),
    "it": ("italiano", "italian"),
    "nl": ("nederlands", "dutch"),
}

RULE_MISSING_FILE = "missing-file"
RULE_UNREADABLE = "unreadable"
RULE_NOT_A_MAPPING = "not-a-mapping"
RULE_APP_NAME = "app-name"
RULE_UI_NAME_EMPTY = "ui-name-empty"
RULE_UI_DESCRIPTION_EMPTY = "ui-description-empty"
RULE_SYSTEM_PROMPT_EMPTY = "system-prompt-empty"
RULE_SYSTEM_PROMPT_COMPANY = "system-prompt-company"
RULE_SYSTEM_PROMPT_LANGUAGE = "system-prompt-language"
RULE_LANGUAGE_EMPTY = "language-empty"
RULE_LANGUAGE_MISMATCH = "language-mismatch"
RULE_PRIMARY_COLOR_FORMAT = "primary-color-format"
RULE_PRIMARY_COLOR_CONTRAST = "primary-color-contrast"
RULE_QUERIES_COUNT = "queries-count"
RULE_LABEL_EMPTY = "label-empty"
RULE_LABEL_LONG = "label-long"
RULE_LABEL_DUPLICATE = "label-duplicate"
RULE_MESSAGE_EMPTY = "message-empty"
RULE_PAGE_EMPTY = "page-empty"
RULE_PAGE_MISSING = "page-missing"
RULE_QUOTE_EMPTY = "quote-empty"
RULE_QUOTE_SHORT = "quote-short"
RULE_QUOTE_NOT_IN_PAGE = "quote-not-in-page"


class CheckFailure(Event):
    field: str
    rule: str


class CheckResult(Event):
    failures: list[CheckFailure] = Field(default_factory=list)

    @property
    def lines(self) -> list[str]:
        return [f"{item.field}: {item.rule}" for item in self.failures]


def relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    red, green, blue = linear
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(a: str, b: str) -> float:
    high = max(relative_luminance(a), relative_luminance(b))
    low = min(relative_luminance(a), relative_luminance(b))
    return (high + 0.05) / (low + 0.05)


def check(directory: Path) -> CheckResult:
    loaded = _load_raw(directory / TAILOR_FILE)
    if isinstance(loaded, CheckResult):
        return loaded
    return CheckResult(failures=_failures(loaded, directory))


def _failures(fields: dict, directory: Path) -> list[CheckFailure]:
    brand = _load_brand(directory)
    company = _str_field(brand, "site_name") or _str_field(fields, "ui_name")
    failures = _scalar_failures(fields, brand)
    failures.extend(
        _system_prompt_failures(_str_field(fields, "system_prompt"), company, _str_field(fields, "language"))
    )
    failures.extend(_queries_failures(fields.get("queries"), directory))
    return failures


def _scalar_failures(fields: dict, brand: dict) -> list[CheckFailure]:
    failures: list[CheckFailure] = []
    if APP_NAME_PATTERN.fullmatch(_str_field(fields, "app_name")) is None:
        failures.append(_failure("app_name", RULE_APP_NAME))
    if not _str_field(fields, "ui_name").strip():
        failures.append(_failure("ui_name", RULE_UI_NAME_EMPTY))
    if not _str_field(fields, "ui_description").strip():
        failures.append(_failure("ui_description", RULE_UI_DESCRIPTION_EMPTY))
    failures.extend(_color_failures(_str_field(fields, "primary_color")))
    failures.extend(_language_failures(_str_field(fields, "language"), brand))
    return failures


def _language_failures(language: str, brand: dict) -> list[CheckFailure]:
    if not language.strip():
        return [_failure("language", RULE_LANGUAGE_EMPTY)]
    brand_language = _str_field(brand, "language")
    if brand_language and language != brand_language:
        return [_failure("language", RULE_LANGUAGE_MISMATCH)]
    return []


def _color_failures(color: str) -> list[CheckFailure]:
    if PRIMARY_COLOR_PATTERN.fullmatch(color) is None:
        return [_failure("primary_color", RULE_PRIMARY_COLOR_FORMAT)]
    if contrast_ratio(color, WHITE) < MIN_CONTRAST:
        return [_failure("primary_color", RULE_PRIMARY_COLOR_CONTRAST)]
    return []


def _system_prompt_failures(prompt: str, company: str, language: str) -> list[CheckFailure]:
    if not prompt.strip():
        return [_failure("system_prompt", RULE_SYSTEM_PROMPT_EMPTY)]
    lowered = prompt.lower()
    failures: list[CheckFailure] = []
    if company.strip() and company.strip().lower() not in lowered:
        failures.append(_failure("system_prompt", RULE_SYSTEM_PROMPT_COMPANY))
    names = LANGUAGE_NAMES.get(language)
    if names and not any(name in lowered for name in names):
        failures.append(_failure("system_prompt", RULE_SYSTEM_PROMPT_LANGUAGE))
    return failures


def _queries_failures(queries: object, directory: Path) -> list[CheckFailure]:
    if not isinstance(queries, list) or len(queries) != QUERY_COUNT:
        return [_failure("queries", RULE_QUERIES_COUNT)]
    failures: list[CheckFailure] = []
    for index, item in enumerate(queries, start=1):
        failures.extend(_query_failures(index, item, directory))
    failures.extend(_label_failures(queries))
    return failures


def _query_failures(index: int, item: object, directory: Path) -> list[CheckFailure]:
    fields = item if isinstance(item, dict) else {}
    prefix = f"queries[{index}]"
    label, message = _str_field(fields, "label"), _str_field(fields, "message")
    page, quote = _str_field(fields, "page"), _str_field(fields, "quote")
    failures: list[CheckFailure] = []
    if not label.strip():
        failures.append(_failure(f"{prefix}.label", RULE_LABEL_EMPTY))
    elif len(label) > LABEL_MAX:
        failures.append(_failure(f"{prefix}.label", RULE_LABEL_LONG))
    if not message.strip():
        failures.append(_failure(f"{prefix}.message", RULE_MESSAGE_EMPTY))
    source: str | None = None
    if not page.strip():
        failures.append(_failure(f"{prefix}.page", RULE_PAGE_EMPTY))
    elif (source := _page_source(directory, page)) is None:
        failures.append(_failure(f"{prefix}.page", RULE_PAGE_MISSING))
    if not quote.strip():
        failures.append(_failure(f"{prefix}.quote", RULE_QUOTE_EMPTY))
    elif len(quote.split()) < QUOTE_MIN_WORDS:
        failures.append(_failure(f"{prefix}.quote", RULE_QUOTE_SHORT))
    elif source is not None and prose.collapse(quote) not in prose.collapse(prose.page_prose(source)):
        failures.append(_failure(f"{prefix}.quote", RULE_QUOTE_NOT_IN_PAGE))
    return failures


def _label_failures(queries: list) -> list[CheckFailure]:
    counts: dict[str, int] = {}
    for item in queries:
        label = _label(item)
        if label.strip():
            counts[label] = counts.get(label, 0) + 1
    failures: list[CheckFailure] = []
    for index, item in enumerate(queries, start=1):
        label = _label(item)
        if label.strip() and counts[label] > 1:
            failures.append(_failure(f"queries[{index}].label", RULE_LABEL_DUPLICATE))
    return failures


def _label(item: object) -> str:
    return _str_field(item, "label") if isinstance(item, dict) else ""


def _page_source(directory: Path, page: str) -> str | None:
    if "/" in page or "\\" in page or ".." in page:
        return None
    try:
        return (directory / PAGES_DIR / f"{page}.md").read_text()
    except OSError:
        return None


def _load_brand(directory: Path) -> dict:
    path = directory / BRAND_FILE
    if not path.is_file():
        return {}
    try:
        return parse.parse_dict(path)
    except PayloadError:
        return {}


def _load_raw(path: Path) -> dict | CheckResult:
    if not path.is_file():
        return _file_result(RULE_MISSING_FILE)
    try:
        return parse.parse_dict(path)
    except PayloadError as exc:
        rule = RULE_NOT_A_MAPPING if exc.message == "not a dictionary" else RULE_UNREADABLE
        return _file_result(rule)


def _str_field(fields: dict, key: str) -> str:
    value = fields.get(key, "")
    return value if isinstance(value, str) else ""


def _failure(field: str, rule: str) -> CheckFailure:
    return CheckFailure(field=field, rule=rule)


def _file_result(rule: str) -> CheckResult:
    return CheckResult(failures=[_failure(TAILOR_FILE, rule)])
