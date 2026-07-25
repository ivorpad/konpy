"""`konpy init` implementation: write a strict, opinionated starter konpy.json.

Gives a cold-start agent (or human) a valid config that already enforces a
best-in-class Python layout (src layout, barrel-only __init__.py, typing and
docstring coverage, size caps, duplication ratchets, unused-code detection)
instead of a "Could not read config file" dead end. Never overwrites an
existing config. The template itself lives in `_init_template.json` next to
this module so it ships as package data and stays real, lintable JSON.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import typer

from konpy.config.loader import CONFIG_FILENAME

INIT_TEMPLATE = (
    resources.files("konpy").joinpath("cli/_init_template.json").read_text(encoding="utf-8")
)

_NEXT_STEPS = """\
Next steps:
  konpy check               run the conventions against this codebase
  konpy docs configuration  full konpy.json reference
  konpy docs predicates     browse the available predicates
  konpy explain             render the config as guidance for a code-writing agent"""


def run_init_command() -> int:
    """Write a strict starter konpy.json into the current directory, never overwriting."""
    target = Path.cwd() / CONFIG_FILENAME
    if target.exists():
        typer.echo(
            f"{CONFIG_FILENAME} already exists here; not overwriting. Edit it "
            "directly, or run 'konpy docs configuration' for the format.",
            err=True,
        )
        return 1

    try:
        target.write_text(INIT_TEMPLATE, encoding="utf-8")
    except OSError as error:
        typer.echo(f"Could not write {CONFIG_FILENAME}: {error}", err=True)
        return 1

    typer.echo(
        f"Wrote {CONFIG_FILENAME} (strict starter: src layout, barrel-only "
        "__init__.py, typing and docstring coverage, 300-line module cap, "
        "duplication ratchets, unused-code detection)."
    )
    typer.echo(_NEXT_STEPS)
    return 0


__all__ = [
    "INIT_TEMPLATE",
    "run_init_command",
]
