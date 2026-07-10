"""`version`, `explain`, and `infer` command registrations for the `konpy` CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from konpy._version import __version__
from konpy.cli._app_instance import app
from konpy.cli.explain import ExplainFormat, run_explain_command
from konpy.cli.infer import InferReportFormat, run_infer_command


@app.command()
def version() -> None:
    """Print the version number."""
    typer.echo(__version__)


@app.command()
def explain(
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


@app.command()
def infer(
    include: Annotated[
        list[str] | None,
        typer.Option(
            "--include",
            help="Glob(s) of files to scan. May be repeated. Default: **/*.py",
        ),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude",
            help="Glob(s) to exclude from scanning. May be repeated.",
        ),
    ] = None,
    test_glob: Annotated[
        list[str] | None,
        typer.Option(
            "--test-glob",
            help=(
                "Glob(s) identifying test files. May be repeated. Default: "
                "tests/**, test_*.py, *_test.py, conftest.py"
            ),
        ),
    ] = None,
    min_confidence: Annotated[
        float,
        typer.Option(
            "--min-confidence",
            help="Minimum support/total ratio required to emit a proposal.",
        ),
    ] = 0.9,
    min_support: Annotated[
        int,
        typer.Option(
            "--min-support",
            help="Minimum sample size (denominator) required before a signal is considered.",
        ),
    ] = 3,
    max_violators: Annotated[
        int,
        typer.Option(
            "--max-violators",
            help="Maximum violator paths listed per proposal in the report.",
        ),
    ] = 10,
    heuristic: Annotated[
        list[str] | None,
        typer.Option(
            "--heuristic",
            help=(
                "Restrict to specific heuristics (repeatable): export-suffix, "
                "paired-test-file, docstring-coverage, annotate-functions-coverage, "
                "barrel-usage, import-dominance, repeated-literals, "
                "duplicate-functions. Default: all."
            ),
        ),
    ] = None,
    format_: Annotated[
        InferReportFormat,
        typer.Option(
            "--format",
            help="Report format: text, markdown, or json.",
        ),
    ] = InferReportFormat.TEXT,
    output_path: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the proposed reusable convention pack here instead of stdout.",
        ),
    ] = None,
    report_path: Annotated[
        str | None,
        typer.Option(
            "--report",
            "-r",
            help="Write the confidence/violators report here instead of stderr.",
        ),
    ] = None,
) -> None:
    """Mine the codebase for candidate structural conventions."""
    exit_code = run_infer_command(
        include=include,
        exclude=exclude,
        test_glob=test_glob,
        min_confidence=min_confidence,
        min_support=min_support,
        max_violators=max_violators,
        heuristic=heuristic,
        format=format_,
        output_path=output_path,
        report_path=report_path,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
