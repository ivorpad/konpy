"""`improve` command registration for the `konpy` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli.agent_runner import DEFAULT_MODEL, ExtractAgent
from konpy.cli.improve import DEFAULT_TIMEOUT, run_improve_command


@app.command()
def improve(
    group: Annotated[
        str | None,
        typer.Option(
            "--group",
            help=(
                "Duplicate-function group name to target. Default: the "
                "top-ranked group from the report's duplication lane."
            ),
        ),
    ] = None,
    agent: Annotated[
        ExtractAgent,
        typer.Option(
            "--agent",
            help="Agent CLI to use: auto, claude, or codex.",
        ),
    ] = ExtractAgent.AUTO,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Model passed through to the agent CLI. Default: sonnet.",
        ),
    ] = DEFAULT_MODEL,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the proposing agent subprocess.",
        ),
    ] = DEFAULT_TIMEOUT,
    output_path: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the proposed diff here instead of stdout.",
        ),
    ] = None,
    config_path: Annotated[
        str | None,
        typer.Option(
            "--config-path",
            help="Path to konpy.json; only its directory anchors the scan root.",
        ),
    ] = None,
) -> None:
    """Propose a reviewable diff for one duplication finding. Never applies it."""
    exit_code = run_improve_command(
        group_name=group,
        agent=agent,
        model=model,
        timeout=timeout,
        output_path=output_path,
        config_path=config_path,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
