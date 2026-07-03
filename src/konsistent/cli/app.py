from __future__ import annotations

import sys

import typer

from konsistent._version import __version__
from konsistent.cli import _commands_agentic as _commands_agentic
from konsistent.cli import _commands_check as _commands_check
from konsistent.cli import _commands_misc as _commands_misc
from konsistent.cli import _help_text as _help_text
from konsistent.cli._app_instance import app
from konsistent.cli._argv import _preprocess_argv

__all__ = ["app", "main"]


def main() -> None:
    """Entry point for the `konsistent` console script."""
    raw_args = sys.argv[1:]
    if raw_args == ["--version"]:
        typer.echo(__version__)
        return

    app(args=_preprocess_argv(raw_args))
