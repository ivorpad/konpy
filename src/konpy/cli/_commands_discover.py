"""`init`, `docs`, and `report` command registrations for the `konpy` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli._init_agents import run_init_agents_command
from konpy.cli.docs import run_docs_command
from konpy.cli.init import run_init_command
from konpy.cli.report import run_report_command


@app.command()
def init(
    agents: Annotated[
        bool,
        typer.Option(
            "--agents",
            help=(
                "Also scaffold AGENTS.md, .claude/settings.json hook wiring, and a "
                "konpy.json verify roster. Never overwrites an existing artifact "
                "(a .gitignore missing a .konpy/ entry is the one exception)."
            ),
        ),
    ] = False,
) -> None:
    """Write a strict starter konpy.json into the current directory."""
    exit_code = run_init_agents_command() if agents else run_init_command()
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def report(
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude",
            help=(
                "Additional glob patterns to drop from every report lane and "
                "from the file/LOC header. Repeatable (--exclude a/** "
                "--exclude b/**), space-separated, or comma-separated "
                "(--exclude 'a/**,b/**'). Commas inside {...} alternation are "
                "preserved. Additive on top of the built-in vendored/build "
                "excludes; does not affect the konpy.json conventions lane."
            ),
        ),
    ] = None,
    include_vendored: Annotated[
        bool,
        typer.Option(
            "--include-vendored",
            help=(
                "Count cookiecutter scaffolds, vendored snapshot dirs, and "
                "gitignored files like any other source instead of dropping "
                "them from the file/LOC header and every in-process lane. "
                "Detection still runs, so duplicate groups confined to those "
                "trees keep their [generator template]/[vendored] label."
            ),
        ),
    ] = False,
) -> None:
    """Run the zero-config codebase report (what bare `konpy` runs)."""
    exit_code = run_report_command(exclude=exclude, include_vendored=include_vendored)
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def docs(
    topic: Annotated[
        str | None,
        typer.Argument(
            help="Reference topic to print, e.g. predicates or configuration.",
        ),
    ] = None,
) -> None:
    """Print bundled reference docs; run without a topic to list them."""
    exit_code = run_docs_command(topic=topic)
    if exit_code != 0:
        raise typer.Exit(exit_code)
