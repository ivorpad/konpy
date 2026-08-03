"""`verify` command registration for the `konpy` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli.verify import run_verify_command


@app.command()
def verify(
    config_path: Annotated[
        str | None,
        typer.Option(
            "--config-path",
            help="Path to konpy.json config file.",
        ),
    ] = None,
) -> None:
    """Run the config-declared verification-step roster (the `verify` section)."""
    exit_code = run_verify_command(config_path=config_path)
    if exit_code != 0:
        raise typer.Exit(exit_code)
