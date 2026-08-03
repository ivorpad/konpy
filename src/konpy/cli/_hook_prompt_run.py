"""Single-prompt verification orchestration for `konpy hook`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from konpy.cli._hook_findings import HookFinding
from konpy.cli._hook_support import HookPayload, build_hook_prompt, parse_verdict
from konpy.cli._review_outcome import (
    ReviewFinding,
    ReviewOutcome,
    combined_review_status,
)
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
    stop_on_first_failure: bool,
    command_name: str,
) -> ReviewOutcome:
    """Run the existing single-prompt verifier once per matched path.

    With `stop_on_first_failure=True`, an agent-run failure, an invalid
    verdict, or the first fail verdict all stop processing immediately
    (this is deliberate cost control: each additional path is another agent
    subprocess). With `stop_on_first_failure=False`, every path is verified
    and infra/verdict problems are collected as warnings rather than
    aborting.

    `command_name` (e.g. `"hook"` or `"review"`) names the calling command in
    any `--log` write-failure warning, so the message matches whichever
    command is actually running.
    """
    findings: list[ReviewFinding] = []
    warnings: list[str] = []
    saw_unavailable = False
    saw_invalid_response = False

    for path in paths:
        run_result = run_verifier(
            build_hook_prompt(
                file_path=path,
                cwd=payload.cwd or "",
                user_prompt=prompt,
            )
        )
        if _agent_run_failed(invocation, run_result, write_error):
            if stop_on_first_failure:
                return ReviewOutcome(status="unavailable")
            saw_unavailable = True
            warnings.append(
                f'Agent CLI "{invocation.agent}" exited with code '
                f"{run_result.returncode} for {path}."
            )
            continue

        verdict = parse_verdict(run_result.stdout)
        if verdict is None:
            write_error(
                f'Agent CLI "{invocation.agent}" did not return a valid verdict.'
            )
            if stop_on_first_failure:
                return ReviewOutcome(status="invalid-response")
            saw_invalid_response = True
            warnings.append(
                f'Agent CLI "{invocation.agent}" did not return a valid '
                f"verdict for {path}."
            )
            continue
        if verdict["verdict"] == "pass":
            continue

        reasons = verdict["reasons"] or [f"Verification failed for {path}."]
        for reason in reasons:
            write_error(reason)

        finding_warnings: list[str] = []
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
                write_error(f"konpy {command_name}: --log warning: {result.error}")
                finding_warnings.append(result.error)

        findings.append(ReviewFinding(path=path, reasons=tuple(reasons)))
        if stop_on_first_failure:
            return ReviewOutcome(
                status="findings",
                findings=tuple(findings),
                warnings=tuple(finding_warnings),
            )
        warnings.extend(finding_warnings)

    return ReviewOutcome(
        status=combined_review_status(
            has_findings=bool(findings),
            saw_invalid_response=saw_invalid_response,
            saw_unavailable=saw_unavailable,
        ),
        findings=tuple(findings),
        warnings=tuple(warnings),
    )


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
