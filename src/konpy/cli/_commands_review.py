"""`hook` and `review` command registrations: agentic PostToolUse checks.

`hook` exits 2 on a verified fail verdict, feeding stderr back to the agent
for a follow-up fix (PostToolUse cannot actually block — the write has
already landed); `review` is the advisory sibling that never exits 2 (see
`konpy.cli.review` for why).
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from konpy.cli._app_instance import app
from konpy.cli.agent_runner import DEFAULT_MODEL
from konpy.cli.hook import DEFAULT_TIMEOUT, run_hook_command
from konpy.cli.review import run_review_command


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
    """Deprecated: prefer konpy review (advisory) or konpy gate (deterministic blocking).

    Run an agentic PostToolUse verification hook.
    """
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


@app.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
def review(
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
                "values exit 1; a missing agent CLI only warns."
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
    """Run an advisory PostToolUse review; findings never block a write."""
    if ctx.args:
        sys.stderr.write(
            f"Unrecognized arguments for konpy review: {' '.join(ctx.args)}\n"
        )
        raise typer.Exit(1)

    exit_code = run_review_command(
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
