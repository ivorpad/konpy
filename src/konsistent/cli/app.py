from __future__ import annotations

import sys
from typing import Annotated

import typer

from konsistent._version import __version__
from konsistent.cli.check import DiagnosticLevel, OutputFormat, run_check_command
from konsistent.cli.explain import ExplainFormat, run_explain_command
from konsistent.cli.extract_rules import ExtractAgent, run_extract_rules_command
from konsistent.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konsistent.config.deprecation_warnings import collect_deprecation_warnings
from konsistent.config.errors import Err
from konsistent.config.loader import load_config_runtime

_KNOWN_SUBCOMMANDS = {"check", "validate", "extract-rules", "explain", "version", "help"}

app = typer.Typer(
    help="Enforce structural conventions in Python codebases.",
    add_completion=False,
)


def _preprocess_argv(argv: list[str]) -> list[str]:
    if argv == ["--version"]:
        return ["version"]

    has_subcommand = any(
        not arg.startswith("-") and arg in _KNOWN_SUBCOMMANDS for arg in argv
    )
    has_help_flag = "--help" in argv or "-h" in argv

    if has_subcommand or has_help_flag:
        return argv

    return ["check", *argv]


@app.callback()
def _callback(
    version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print the version number.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Enforce structural conventions in Python codebases."""
    if version_flag:
        typer.echo(__version__)
        raise typer.Exit()


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
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command()
def version() -> None:
    """Print the version number."""
    typer.echo(__version__)


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


@app.command()
def explain(
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
        ExplainFormat,
        typer.Option(
            "--format",
            help="Output format: md or text.",
        ),
    ] = ExplainFormat.MD,
    placeholder: Annotated[
        list[str] | None,
        typer.Option(
            "--placeholder",
            help='Inject a placeholder value. Format: "name:value". May be repeated.',
        ),
    ] = None,
) -> None:
    """Render resolved conventions as prevention-side guidance for a code-writing agent."""
    exit_code = run_explain_command(
        config_path=config_path,
        config_package=config_package,
        placeholder=placeholder,
        format=format_,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command(name="extract-rules")
def extract_rules(
    source_file: Annotated[
        str,
        typer.Argument(
            help="Markdown/text source to extract reusable convention rules from.",
        ),
    ],
    output_path: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Path for the generated reusable convention pack proposal.",
        ),
    ] = None,
    agent: Annotated[
        ExtractAgent,
        typer.Option(
            "--agent",
            help="Agent CLI to use: auto, claude, or codex.",
        ),
    ] = ExtractAgent.AUTO,
    report_path: Annotated[
        str | None,
        typer.Option(
            "--report",
            help="Write unmapped-rules report to this path instead of stdout.",
        ),
    ] = None,
) -> None:
    """Extract reviewable reusable conventions from a prose source file."""
    exit_code = run_extract_rules_command(
        source_file=source_file,
        output_path=output_path,
        agent=agent,
        report_path=report_path,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command(name="help")
def help_command() -> None:
    """Show this help message."""
    typer.echo(
        f"""konsistent v{__version__} — Enforce structural conventions in Python codebases

Usage:
  konsistent [command] [options]

Commands:
  check          Check structural conventions (default)
  validate       Validate configuration
  extract-rules  Extract reusable convention proposals from prose rules
  explain        Render resolved conventions as agent guidance (markdown/text)
  version        Print the version number
  help           Show this help message

Check options:
  --config-path <path>       Path to konsistent.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: default, json, github, markdown
  --verbose                  Accepted for upstream compatibility
  --max-diagnostics <n>      Maximum diagnostics to report (default: 100)
  --colors / --no-colors     Enable or disable colored default output
  --error-on-warnings        Treat warnings as errors for exit code purposes
  --diagnostic-level <level> Minimum severity to evaluate: warning or error
  --placeholder <name:value> Inject a placeholder value; may be repeated
  --show-suppressed          List diagnostics suppressed by source comments

Validate options:
  --config-path <path>       Path to konsistent.json config file
  --config-package <pkg>     Unsupported in the Python port
  --placeholder <name:value> Inject a placeholder value; may be repeated

Extract-rules options:
  -o, --output <path>        Path for generated reusable convention pack proposal
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write unmapped-rules report to this path

Explain options:
  --config-path <path>       Path to konsistent.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: md, text
  --placeholder <name:value> Inject a placeholder value; may be repeated

Global options:
  --help, -h                 Show help
  --version                  Print the version number"""
    )


def main() -> None:
    raw_args = sys.argv[1:]
    if raw_args == ["--version"]:
        typer.echo(__version__)
        return

    app(args=_preprocess_argv(raw_args))


__all__ = ["_preprocess_argv", "app", "main"]
