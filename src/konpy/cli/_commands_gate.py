"""`gate` command registration for the `konpy` CLI."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli.check import DiagnosticLevel
from konpy.cli.gate import run_gate_command


@app.command(
    name="gate",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def gate(
    ctx: typer.Context,
    match: Annotated[
        list[str] | None,
        typer.Option(
            "--match",
            help=(
                "Glob pattern to filter proposed write paths against. May be "
                "repeated. If omitted, every target path is gated."
            ),
        ),
    ] = None,
    config_path: Annotated[
        str | None,
        typer.Option(
            "--config-path",
            help="Path to konpy.json config file.",
        ),
    ] = None,
    config_package: Annotated[
        str | None,
        typer.Option(
            "--config-package",
            help="NPM package name to load config from. Unsupported in the Python port.",
        ),
    ] = None,
    diagnostic_level: Annotated[
        DiagnosticLevel,
        typer.Option(
            "--diagnostic-level",
            help="Minimum diagnostic severity to evaluate.",
        ),
    ] = DiagnosticLevel.WARNING,
    error_on_warnings: Annotated[
        bool,
        typer.Option(
            "--error-on-warnings",
            help="Block proposed writes on warnings as well as errors.",
        ),
    ] = False,
    placeholder: Annotated[
        list[str] | None,
        typer.Option(
            "--placeholder",
            help='Inject a placeholder value. Format: "name:value". May be repeated.',
        ),
    ] = None,
    max_diagnostics: Annotated[
        int,
        typer.Option(
            "--max-diagnostics",
            help="Maximum number of diagnostics to report when blocking.",
        ),
    ] = 100,
    fail_closed: Annotated[
        bool,
        typer.Option(
            "--fail-closed",
            help=(
                "Block the write when deterministic verification cannot run, "
                "instead of failing open."
            ),
        ),
    ] = False,
    baseline: Annotated[
        str | None,
        typer.Option(
            "--baseline",
            help=(
                "Path to the baseline file. Defaults to konpy.baseline.json next "
                "to the resolved config file. Pre-existing baselined violations "
                "never block a proposed write; new ones still do."
            ),
        ),
    ] = None,
    ruff: Annotated[
        bool,
        typer.Option(
            "--ruff",
            help=(
                "Also run `ruff check` against every proposed .py write, using "
                "the target repo's own ruff config. Findings block like any "
                "other verified violation. A missing ruff executable follows "
                "the same fail-open/--fail-closed contract as any other "
                "verification-unavailable case."
            ),
        ),
    ] = False,
) -> None:
    """Run a deterministic Claude Code PreToolUse gate against proposed content."""
    if ctx.args:
        sys.stderr.write(
            f"Unrecognized arguments for konpy gate: {' '.join(ctx.args)}\n"
        )
        raise typer.Exit(1)

    exit_code = run_gate_command(
        match=match or [],
        config_path=config_path,
        config_package=config_package,
        diagnostic_level=diagnostic_level,
        error_on_warnings=error_on_warnings,
        placeholder=placeholder,
        max_diagnostics=max_diagnostics,
        fail_closed=fail_closed,
        baseline=baseline,
        ruff=ruff,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
