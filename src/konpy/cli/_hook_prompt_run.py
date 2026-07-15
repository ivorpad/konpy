"""Single-prompt verification orchestration for `konpy hook`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from konpy.cli._hook_findings import HookFinding
from konpy.cli._hook_support import HookPayload, build_hook_prompt, parse_verdict
from konpy.cli.agent_runner import AgentInvocation, AgentRunResult
from konpy.config.errors import Err, Result

type RunVerifier = Callable[[str], AgentRunResult]
type AppendFinding = Callable[[str | Path, HookFinding], Result[None]]
type WriteError = Callable[[str], None]


def run_prompt_verifications(
    *,
    paths: Sequence[str],
    prompt: str,
    payload: HookPayload,
    invocation: AgentInvocation,
    agent_value: str,
    model: str,
    log_path: str | None,
    run_verifier: RunVerifier,
    append_finding: AppendFinding,
    write_error: WriteError,
) -> int:
    """Run the existing single-prompt verifier once per matched path."""
    for path in paths:
        run_result = run_verifier(
            build_hook_prompt(
                file_path=path,
                cwd=payload.cwd or "",
                user_prompt=prompt,
            )
        )
        if _agent_run_failed(invocation, run_result, write_error):
            return 1

        verdict = parse_verdict(run_result.stdout)
        if verdict is None:
            write_error(
                f'Agent CLI "{invocation.agent}" did not return a valid verdict.'
            )
            return 1
        if verdict["verdict"] == "pass":
            continue

        reasons = verdict["reasons"] or [f"Verification failed for {path}."]
        for reason in reasons:
            write_error(reason)

        if log_path is not None:
            result = append_finding(
                log_path,
                HookFinding(
                    loggedAt=datetime.now(UTC).isoformat(),
                    sessionId=payload.session_id,
                    cwd=payload.cwd,
                    toolName=payload.tool_name,
                    filePath=path,
                    prompt=prompt,
                    agent=agent_value,
                    model=model,
                    reasons=reasons,
                ),
            )
            if isinstance(result, Err):
                write_error(f"konpy hook: --log warning: {result.error}")
        return 2

    return 0


def _agent_run_failed(
    invocation: AgentInvocation,
    result: AgentRunResult,
    write_error: WriteError,
) -> bool:
    if result.returncode == 0:
        return False

    write_error(
        f'Agent CLI "{invocation.agent}" exited with code {result.returncode}.'
    )
    if result.stderr.strip():
        write_error(result.stderr.strip())
    elif result.stdout.strip():
        write_error(result.stdout.strip())
    return True


__all__ = ["run_prompt_verifications"]
