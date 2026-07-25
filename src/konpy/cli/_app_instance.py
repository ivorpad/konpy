"""The shared Typer application instance for `konpy`.

Command modules import `app` from here and register themselves onto it via
`@app.command()`; `konpy.cli.app` imports those modules for their
registration side effects and re-exports `app` as the public facade.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="Enforce structural conventions in Python codebases.",
    epilog=(
        "Run 'konpy help' for the full option reference, 'konpy init' to create "
        "a starter konpy.json, and 'konpy docs' for the bundled reference docs."
    ),
    add_completion=False,
)


@app.callback()
def _callback(
    version_flag: bool = typer.Option(
        False,
        "--version",
        help="Print the version number.",
        is_eager=True,
    ),
) -> None:
    """Enforce structural conventions in Python codebases."""
    if version_flag:
        from konpy._version import __version__

        typer.echo(__version__)
        raise typer.Exit()
