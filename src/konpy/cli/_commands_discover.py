"""`init`, `docs`, and `report` command registrations for the `konpy` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli.docs import run_docs_command
from konpy.cli.init import run_init_command
from konpy.cli.report import run_report_command


@app.command()
def init() -> None:
    """Write a strict starter konpy.json into the current directory."""
    exit_code = run_init_command()
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
) -> None:
    """Run the zero-config codebase report (what bare `konpy` runs)."""
    exit_code = run_report_command(exclude=exclude)
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
