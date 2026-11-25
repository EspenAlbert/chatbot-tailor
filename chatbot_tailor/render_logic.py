"""Render a checked site directory into `out/{app_name}`.

`render` runs `check` first, then writes one `main.tf`, a `docs/` copy of
`pages/`, and an `assets/` overlay. The overlay starts from two aws-chatbot
templates vendored under `templates/aws_chatbot`: `config.toml` carries the
UI name and description, and `theme.css` carries the brand primary in HSL
channels for both light and dark mode.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

from model_lib import Event, parse
from pydantic import Field
from zero_3rdparty import file_utils

from chatbot_tailor import brand, check_logic

TEMPLATES_DIR = Path(__file__).parent / "templates" / "aws_chatbot"
THEME_TEMPLATE = TEMPLATES_DIR / "theme.css"
CONFIG_TEMPLATE = TEMPLATES_DIR / "config.toml"
LIGHT_PLACEHOLDER = "__PRIMARY_LIGHT__"
DARK_PLACEHOLDER = "__PRIMARY_DARK__"
NAME_PLACEHOLDER = "__UI_NAME__"
DESCRIPTION_PLACEHOLDER = "__UI_DESCRIPTION__"
DARK_BACKGROUND = "#001e2b"
ASSETS_DIR = "assets"
DOCS_DIR = "docs"
OUT_DIR = "out"
TERRAFORM_COMMANDS: tuple[tuple[str, ...], ...] = (("fmt",), ("init", "-backend=false"), ("validate",))
PROVIDERS = """terraform {
  required_version = ">= 1.10"

  required_providers {
    mongodbatlas = {
      source  = "mongodb/mongodbatlas"
      version = "~> 2.16"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "mongodbatlas" {}
"""
OUTPUTS = """output "https_url" {
  description = "CloudFront HTTPS URL for the deployed chat UI."
  value       = module.chatbot.https_url
}

output "chatbot" {
  description = "The chat app's image, login, secret name, and build result."
  value       = module.chatbot.chatbot
}

output "chatbot_login_password" {
  description = "Demo login password (also stored in the app secret)."
  value       = module.chatbot.chatbot_login_password
  sensitive   = true
}
"""


class RenderResult(Event):
    exit_code: int
    out_dir: Path | None = None
    failures: list[str] = Field(default_factory=list)
    detail: str = ""


def _hcl_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _prompt_block(prompt: str) -> str:
    body = "\n".join(f"    {line}" for line in prompt.splitlines())
    return f"  chatbot = {{\n    system_prompt = <<-EOT\n{body}\n    EOT\n  }}"


def _queries_block(queries: list) -> str:
    entries: list[str] = []
    for query in queries:
        entries.append(
            "\n".join(
                [
                    "    {",
                    f"      label = {_hcl_string(query['label'])}",
                    f"      message = {_hcl_string(query['message'])}",
                    "    },",
                ]
            )
        )
    return "\n".join(["  queries = [", *entries, "  ]"])


def _main_tf(fields: dict) -> str:
    module = "\n".join(
        [
            'module "chatbot" {',
            '  source = "terraform-mongodbatlas-modules/aws-chatbot/mongodbatlas"',
            "",
            f"  app_name = {_hcl_string(fields['app_name'])}",
            "",
            _prompt_block(fields["system_prompt"]),
            "",
            _queries_block(fields["queries"]),
            "",
            '  document_dirs = ["${path.module}/docs"]',
            "  skip_repo_docs = true",
            '  assets_dir = "${path.module}/assets"',
            "}",
        ]
    )
    return "\n\n".join(section.rstrip("\n") for section in (PROVIDERS, module, OUTPUTS)) + "\n"


def _hsl(color: str) -> tuple[float, float, float]:
    red, green, blue = (int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
    high, low = max(red, green, blue), min(red, green, blue)
    lightness = (high + low) / 2
    delta = high - low
    if delta == 0:
        return 0.0, 0.0, lightness * 100
    saturation = delta / (1 - abs(2 * lightness - 1))
    if high == red:
        hue = 60 * (((green - blue) / delta) % 6)
    elif high == green:
        hue = 60 * ((blue - red) / delta + 2)
    else:
        hue = 60 * ((red - green) / delta + 4)
    return hue, saturation * 100, lightness * 100


def _hex(hue: float, saturation: float, lightness: float) -> str:
    saturation /= 100
    lightness /= 100
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    secondary = chroma * (1 - abs((hue / 60) % 2 - 1))
    if hue < 60:
        red, green, blue = chroma, secondary, 0.0
    elif hue < 120:
        red, green, blue = secondary, chroma, 0.0
    elif hue < 180:
        red, green, blue = 0.0, chroma, secondary
    elif hue < 240:
        red, green, blue = 0.0, secondary, chroma
    elif hue < 300:
        red, green, blue = secondary, 0.0, chroma
    else:
        red, green, blue = chroma, 0.0, secondary
    offset = lightness - chroma / 2
    channels = (min(255, max(0, round((channel + offset) * 255))) for channel in (red, green, blue))
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _channel(value: float) -> str:
    return f"{round(value, 1):g}"


def hsl_channels(color: str) -> str:
    hue, saturation, lightness = _hsl(color)
    return f"{_channel(hue)} {_channel(saturation)}% {_channel(lightness)}%"


def raise_lightness(color: str, background: str, minimum: float = check_logic.MIN_CONTRAST) -> str:
    if check_logic.contrast_ratio(color, background) >= minimum:
        return color
    hue, saturation, lightness = _hsl(color)
    while lightness < 100:
        lightness = min(lightness + 1, 100)
        candidate = _hex(hue, saturation, lightness)
        if check_logic.contrast_ratio(candidate, background) >= minimum:
            return candidate
    return "#ffffff"


def render_theme(primary_color: str) -> str:
    dark = hsl_channels(raise_lightness(primary_color, DARK_BACKGROUND))
    return (
        THEME_TEMPLATE.read_text()
        .replace(LIGHT_PLACEHOLDER, hsl_channels(primary_color))
        .replace(DARK_PLACEHOLDER, dark)
    )


def _toml_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


def render_config(ui_name: str, ui_description: str) -> str:
    return (
        CONFIG_TEMPLATE.read_text()
        .replace(NAME_PLACEHOLDER, _toml_escape(ui_name))
        .replace(DESCRIPTION_PLACEHOLDER, _toml_escape(ui_description))
    )


def fetch_date(directory: Path) -> date:
    times = [path.stat().st_mtime for path in (directory / check_logic.PAGES_DIR).glob("*.md")]
    if not times:
        return datetime.now(tz=UTC).astimezone().date()
    return datetime.fromtimestamp(max(times), tz=UTC).astimezone().date()


def _page_urls(directory: Path) -> list[str]:
    pages = sorted((directory / check_logic.PAGES_DIR).glob("*.md"))
    return [path.read_text().splitlines()[0] for path in pages]


def render_chainlit_md(directory: Path, ui_name: str) -> str:
    urls = _page_urls(directory)
    lines = [
        f"# {ui_name}",
        "",
        (
            f"{len(urls)} pages fetched on {fetch_date(directory)}. "
            "Ask anything about the site; every answer cites one of these pages."
        ),
        "",
        "## Source pages",
        "",
        *(f"- {url}" for url in urls),
    ]
    return "\n".join(lines) + "\n"


def run_terraform(out_dir: Path, terraform: str) -> str:
    for args in TERRAFORM_COMMANDS:
        completed = subprocess.run([terraform, *args], cwd=out_dir, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            output = completed.stderr.strip() or completed.stdout.strip()
            return f"terraform {args[0]} failed ({completed.returncode}): {output}"
    return ""


def render(directory: Path) -> RenderResult:
    checked = check_logic.check(directory)
    if checked.failures:
        return RenderResult(exit_code=1, failures=checked.lines, detail="check failed")
    fields = parse.parse_dict(directory / check_logic.TAILOR_FILE)
    out_dir = directory / OUT_DIR / str(fields["app_name"])
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    file_utils.ensure_parents_write_text(out_dir / "main.tf", _main_tf(fields))
    shutil.copytree(directory / check_logic.PAGES_DIR, out_dir / DOCS_DIR)
    assets = out_dir / ASSETS_DIR
    ui_name, ui_description = str(fields["ui_name"]), str(fields["ui_description"])
    file_utils.ensure_parents_write_text(assets / ".chainlit" / "config.toml", render_config(ui_name, ui_description))
    file_utils.ensure_parents_write_text(assets / "chainlit.md", render_chainlit_md(directory, ui_name))
    file_utils.ensure_parents_write_text(assets / "public" / "theme.css", render_theme(str(fields["primary_color"])))
    favicon = directory / brand.FAVICON_PATH
    if favicon.is_file():
        favicon_target = assets / "public" / "favicon.svg"
        favicon_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(favicon, favicon_target)
    if terraform := shutil.which("terraform"):
        detail = run_terraform(out_dir, terraform)
        if detail:
            return RenderResult(exit_code=1, out_dir=out_dir, detail=detail)
    return RenderResult(exit_code=0, out_dir=out_dir)
