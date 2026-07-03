"""`extract-rules`, `hook`, and `hook-propose` command registrations for the CLI."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli._hook_findings import DEFAULT_FINDINGS_LOG_PATH
from konpy.cli.agent_runner import DEFAULT_MODEL
from konpy.cli.extract_rules import ExtractAgent, run_extract_rules_command
from konpy.cli.hook import DEFAULT_TIMEOUT, run_hook_command
from konpy.cli.propose import run_propose_command


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


@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def hook(
    ctx: typer.Context,
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
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Model passed through to the agent CLI as --model. Default: sonnet.",
        ),
    ] = DEFAULT_MODEL,
    timeout: Annotated[
        float,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the verifier agent subprocess.",
        ),
    ] = DEFAULT_TIMEOUT,
    log_path: Annotated[
        str | None,
        typer.Option(
            "--log",
            help=(
                "Append verified fail verdicts as JSONL to this path for later "
                "hook-propose."
            ),
        ),
    ] = None,
) -> None:
    """Run an agentic PostToolUse verification hook for Claude Code or Codex."""
    # Unknown options land in ctx.args (ignore_unknown_options) instead of
    # raising Click's UsageError, which exits 2 -- a code reserved exclusively
    # for a verified fail verdict. A misconfigured hook must fail open with 1.
    if ctx.args:
        sys.stderr.write(
            f"Unrecognized arguments for konpy hook: {' '.join(ctx.args)}\n"
        )
        raise typer.Exit(1)

    exit_code = run_hook_command(
        match=match or [],
        prompt=prompt,
        agent=agent,
        model=model,
        timeout=timeout,
        log_path=log_path,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command(name="hook-propose")
def hook_propose(
    findings_path: Annotated[
        str,
        typer.Argument(
            help="JSONL hook findings log to promote into a reusable convention pack.",
        ),
    ] = DEFAULT_FINDINGS_LOG_PATH,
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
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the proposal agent subprocess.",
        ),
    ] = None,
) -> None:
    """Promote aggregated `konpy hook` findings into a reviewable reusable convention pack."""
    exit_code = run_propose_command(
        findings_path=findings_path,
        output_path=output_path,
        agent=agent,
        report_path=report_path,
        model=model,
        timeout=timeout,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
