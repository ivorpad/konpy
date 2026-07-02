from __future__ import annotations

import sys
from typing import Annotated

import typer

from konsistent._version import __version__
from konsistent.cli.agent_runner import DEFAULT_MODEL
from konsistent.cli.check import DiagnosticLevel, OutputFormat, run_check_command
from konsistent.cli.explain import ExplainFormat, run_explain_command
from konsistent.cli.extract_rules import ExtractAgent, run_extract_rules_command
from konsistent.cli.hook import DEFAULT_TIMEOUT, run_hook_command
from konsistent.cli.infer import InferReportFormat, run_infer_command
from konsistent.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konsistent.config.deprecation_warnings import collect_deprecation_warnings
from konsistent.config.errors import Err
from konsistent.config.loader import load_config_runtime

_KNOWN_SUBCOMMANDS = {
    "check",
    "validate",
    "extract-rules",
    "infer",
    "explain",
    "hook",
    "version",
    "help",
}

_MULTI_VALUE_OPTIONS = ("--files",)

app = typer.Typer(
    help="Enforce structural conventions in Python codebases.",
    add_completion=False,
)


def _expand_multi_value_options(argv: list[str]) -> list[str]:
    """Expand a single `--files a.py b.py` occurrence into repeated
    `--files a.py --files b.py` tokens, so `--files` supports both the
    already-native repeated-flag form and a single space-separated list.

    Expansion stops at the first following token that starts with `-`
    (treated as the next option) or at end of argv. Tokens after a literal
    `--` separator are never expanded. `--files=value` (single value via
    `=`) is left untouched — it is already exactly one value and is handled
    natively by Click.
    """
    expanded: list[str] = []
    index = 0
    saw_double_dash = False
    while index < len(argv):
        token = argv[index]
        if token == "--":
            saw_double_dash = True
            expanded.append(token)
            index += 1
            continue
        if saw_double_dash or token not in _MULTI_VALUE_OPTIONS:
            expanded.append(token)
            index += 1
            continue

        index += 1
        values: list[str] = []
        while index < len(argv) and not argv[index].startswith("-"):
            values.append(argv[index])
            index += 1

        if not values:
            expanded.append(token)  # bare flag; let Click raise its own error
            continue

        for value in values:
            expanded.append(token)
            expanded.append(value)

    return expanded


def _preprocess_argv(argv: list[str]) -> list[str]:
    if argv == ["--version"]:
        return ["version"]

    expanded = _expand_multi_value_options(argv)

    has_subcommand = any(
        not arg.startswith("-") and arg in _KNOWN_SUBCOMMANDS for arg in expanded
    )
    has_help_flag = "--help" in expanded or "-h" in expanded

    if has_subcommand or has_help_flag:
        return expanded

    return ["check", *expanded]


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
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Model passed through to the agent CLI as --model. Default: sonnet.",
        ),
    ] = DEFAULT_MODEL,
) -> None:
    """Extract reviewable reusable conventions from a prose source file."""
    exit_code = run_extract_rules_command(
        source_file=source_file,
        output_path=output_path,
        agent=agent,
        report_path=report_path,
        model=model,
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
                "barrel-usage, import-dominance. Default: all."
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


@app.command()
def hook(
    match: Annotated[
        list[str] | None,
        typer.Option(
            "--match",
            help="Glob pattern to filter written/edited files against. May be repeated.",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            help=(
                "Natural-language verification instruction for the agent. "
                "Required; a missing value fails open with exit code 1 rather "
                "than a CLI usage error, so exit code 2 stays reserved for a "
                "verified fail verdict."
            ),
        ),
    ] = None,
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            help=(
                "Verifier agent CLI to use: claude or codex. Required; a "
                "missing or invalid value fails open with exit code 1 rather "
                "than a CLI usage error, so exit code 2 stays reserved for a "
                "verified fail verdict."
            ),
        ),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the verifier agent subprocess.",
        ),
    ] = DEFAULT_TIMEOUT,
) -> None:
    """Run an agentic PostToolUse verification hook for Claude Code or Codex."""
    exit_code = run_hook_command(
        match=match or [],
        prompt=prompt,
        agent=agent,
        timeout=timeout,
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
  infer          Mine the codebase for candidate structural conventions
  explain        Render resolved conventions as agent guidance (markdown/text)
  hook           Run an agentic PostToolUse verification hook
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
  --files <path...>          Restrict checking to these files; repeatable or space-separated
  --changed                  Restrict checking to files changed since HEAD (git diff + untracked)

Validate options:
  --config-path <path>       Path to konsistent.json config file
  --config-package <pkg>     Unsupported in the Python port
  --placeholder <name:value> Inject a placeholder value; may be repeated

Extract-rules options:
  -o, --output <path>        Path for generated reusable convention pack proposal
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write unmapped-rules report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)

Infer options:
  --include <glob>           Glob(s) of files to scan; repeatable (default: **/*.py)
  --exclude <glob>           Glob(s) to exclude from scanning; repeatable
  --test-glob <glob>         Glob(s) identifying test files; repeatable
  --min-confidence <n>       Minimum support/total ratio required to propose (default: 0.9)
  --min-support <n>          Minimum sample size required to consider a signal (default: 3)
  --max-violators <n>        Maximum violator paths listed per proposal (default: 10)
  --heuristic <name>         Restrict to specific heuristics; repeatable
  --format <format>          Report format: text, markdown, json
  -o, --output <path>        Write the proposed reusable convention pack here instead of stdout
  -r, --report <path>        Write the confidence/violators report here instead of stderr

Explain options:
  --config-path <path>       Path to konsistent.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: md, text
  --placeholder <name:value> Inject a placeholder value; may be repeated

Hook options:
  --match <glob>             Glob pattern to filter written/edited files; may be repeated
  --prompt <text>            Natural-language verification instruction (required)
  --agent <agent>            Verifier agent CLI to use: claude or codex (required)
  --timeout <seconds>        Timeout for the verifier agent subprocess (default: 300.0)

Exit codes (hook):
  0  pass, or skipped (no match, non-write tool, sentinel active, unparseable payload)
  1  infra fail-open (missing/invalid --prompt or --agent, agent missing,
     subprocess error, unparseable agent output) -- never a CLI usage error
  2  verdict is fail; reasons are written to stderr

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
