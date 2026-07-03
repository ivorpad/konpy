"""`check` and `validate` command registrations for the `konsistent` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konsistent.cli._app_instance import app
from konsistent.cli.check import DiagnosticLevel, OutputFormat, run_check_command
from konsistent.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konsistent.config.deprecation_warnings import collect_deprecation_warnings
from konsistent.config.errors import Err
from konsistent.config.loader import load_config_runtime


@app.command()
def check(
    config_path: Annotated[
        str | None,
        typer.Option(
            "--config-path",
            help="Path to konsistent.json config file.",
        ),
    ] = None,
    config_package: Annotated[
        str | None,
        typer.Option(
            "--config-package",
            help="NPM package name to load config from. Unsupported in the Python port.",
        ),
    ] = None,
    format_: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output format.",
        ),
    ] = OutputFormat.DEFAULT,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Accepted for upstream compatibility; currently no distinct output.",
        ),
    ] = False,
    max_diagnostics: Annotated[
        int,
        typer.Option(
            "--max-diagnostics",
            help="Maximum number of diagnostics to report.",
        ),
    ] = 100,
    colors: Annotated[
        bool | None,
        typer.Option(
            "--colors/--no-colors",
            help="Enable or disable colored output for the default format.",
        ),
    ] = None,
    error_on_warnings: Annotated[
        bool,
        typer.Option(
            "--error-on-warnings",
            help="Treat warnings as errors for exit code purposes.",
        ),
    ] = False,
    diagnostic_level: Annotated[
        DiagnosticLevel,
        typer.Option(
            "--diagnostic-level",
            help="Minimum diagnostic severity to evaluate.",
        ),
    ] = DiagnosticLevel.WARNING,
    placeholder: Annotated[
        list[str] | None,
        typer.Option(
            "--placeholder",
            help='Inject a placeholder value. Format: "name:value". May be repeated.',
        ),
    ] = None,
    show_suppressed: Annotated[
        bool,
        typer.Option(
            "--show-suppressed",
            help="List diagnostics suppressed by source comments.",
        ),
    ] = False,
    files: Annotated[
        list[str] | None,
        typer.Option(
            "--files",
            help=(
                "Restrict checking to these files. Repeatable "
                "(--files a.py --files b.py) or a single space-separated "
                "occurrence (--files a.py b.py). Mutually exclusive with "
                "--changed. See docs/reference/cli.md for scoping semantics."
            ),
        ),
    ] = None,
    changed: Annotated[
        bool,
        typer.Option(
            "--changed",
            help=(
                "Restrict checking to files changed since HEAD "
                "(git diff --name-only HEAD) plus untracked files "
                "(git ls-files --others --exclude-standard). Mutually "
                "exclusive with --files. Does not reduce unusedCode scan time."
            ),
        ),
    ] = False,
) -> None:
    """Check structural conventions."""
    exit_code = run_check_command(
        config_path=config_path,
        config_package=config_package,
        format=format_,
        verbose=verbose,
        max_diagnostics=max_diagnostics,
        colors=colors,
        error_on_warnings=error_on_warnings,
        diagnostic_level=diagnostic_level,
        placeholder=placeholder,
        show_suppressed=show_suppressed,
        files=files,
        changed=changed,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def validate(
    config_path: Annotated[
        str | None,
        typer.Option(
            "--config-path",
            help="Path to konsistent.json config file.",
        ),
    ] = None,
    config_package: Annotated[
        str | None,
        typer.Option(
            "--config-package",
            help="NPM package name to load config from. Unsupported in the Python port.",
        ),
    ] = None,
    placeholder: Annotated[
        list[str] | None,
        typer.Option(
            "--placeholder",
            help='Inject a placeholder value. Format: "name:value". May be repeated.',
        ),
    ] = None,
) -> None:
    """Validate the konsistent configuration file."""
    cli_placeholders_result = parse_cli_placeholders(
        raw=normalize_placeholder_arg(placeholder),
    )
    if isinstance(cli_placeholders_result, Err):
        typer.echo(cli_placeholders_result.error, err=True)
        raise typer.Exit(1)

    config_result = load_config_runtime(
        config_path=config_path,
        config_package=config_package,
        cli_placeholders=cli_placeholders_result.value,
    )
    if isinstance(config_result, Err):
        typer.echo(config_result.error, err=True)
        raise typer.Exit(1)

    for warning in collect_deprecation_warnings(config=config_result.value.config):
        typer.echo(warning)

    typer.echo("Configuration is valid.")
