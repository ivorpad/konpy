"""`extract-rules`, `hook`, and `hook-propose` command registrations."""

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
            help="Markdown/text source to extract rules from.",
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
    rules_output_path: Annotated[
        str | None,
        typer.Option(
            "--rules-output",
            help="Path for the generated semantic-rules package.",
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
            help="Write the rule-routing report to this path.",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Model passed through to the agent CLI. Default: sonnet.",
        ),
    ] = DEFAULT_MODEL,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the extraction agent subprocess.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Stream the agent CLI's own output to stderr while it runs.",
        ),
    ] = False,
) -> None:
    """Extract reviewable structural and semantic rules from prose."""
    exit_code = run_extract_rules_command(
        source_file=source_file,
        output_path=output_path,
        rules_output_path=rules_output_path,
        agent=agent,
        report_path=report_path,
        model=model,
        timeout=timeout,
        verbose=verbose,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
def hook(
    ctx: typer.Context,
    match: Annotated[
        list[str] | None,
        typer.Option(
            "--match",
            help="Glob filtering written/edited files. May be repeated.",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            help=(
                "One natural-language verification instruction. Exactly one "
                "of --prompt or --rules is required at runtime."
            ),
        ),
    ] = None,
    rules_path: Annotated[
        str | None,
        typer.Option(
            "--rules",
            help=(
                "Semantic-rules package to verify. Exactly one of --prompt "
                "or --rules is required at runtime."
            ),
        ),
    ] = None,
    agent: Annotated[
        str | None,
        typer.Option(
            "--agent",
            help=(
                "Verifier agent CLI: claude or codex. Missing or invalid "
                "values fail open with exit code 1."
            ),
        ),
    ] = None,
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
            help="Timeout in seconds for the verifier subprocess.",
        ),
    ] = DEFAULT_TIMEOUT,
    log_path: Annotated[
        str | None,
        typer.Option(
            "--log",
            help="Append verified fail findings as JSONL for hook-propose.",
        ),
    ] = None,
) -> None:
    """Run an agentic PostToolUse verification hook."""
    if ctx.args:
        sys.stderr.write(
            f"Unrecognized arguments for konpy hook: {' '.join(ctx.args)}\n"
        )
        raise typer.Exit(1)

    exit_code = run_hook_command(
        match=match or [],
        prompt=prompt,
        rules_path=rules_path,
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
            help="JSONL hook findings log to promote into rule proposals.",
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
    rules_output_path: Annotated[
        str | None,
        typer.Option(
            "--rules-output",
            help="Path for the generated semantic-rules package.",
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
            help="Write the rule-routing report to this path.",
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help="Model passed through to the agent CLI. Default: sonnet.",
        ),
    ] = DEFAULT_MODEL,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            help="Timeout in seconds for the proposal agent subprocess.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Stream the agent CLI's own output to stderr while it runs.",
        ),
    ] = False,
) -> None:
    """Promote hook findings into structural and semantic proposals."""
    exit_code = run_propose_command(
        findings_path=findings_path,
        output_path=output_path,
        rules_output_path=rules_output_path,
        agent=agent,
        report_path=report_path,
        model=model,
        timeout=timeout,
        verbose=verbose,
    )
    if exit_code != 0:
        raise typer.Exit(exit_code)
