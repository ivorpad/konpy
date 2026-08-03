from __future__ import annotations

import sys

import typer

from konpy._version import __version__
from konpy.cli import _commands_agentic as _commands_agentic
from konpy.cli import _commands_check as _commands_check
from konpy.cli import _commands_discover as _commands_discover
from konpy.cli import _commands_gate as _commands_gate
from konpy.cli import _commands_improve as _commands_improve
from konpy.cli import _commands_misc as _commands_misc
from konpy.cli import _commands_review as _commands_review
from konpy.cli import _commands_verify as _commands_verify
from konpy.cli import _help_text as _help_text
from konpy.cli._app_instance import app
from konpy.cli._argv import _preprocess_argv

__all__ = ["app", "main"]


def main() -> None:
    """Entry point for the `konpy` console script."""
    raw_args = sys.argv[1:]
    if raw_args == ["--version"]:
        typer.echo(__version__)
        return

    app(args=_preprocess_argv(raw_args))
