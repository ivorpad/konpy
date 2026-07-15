"""Semantic-rules verification orchestration for `konpy hook`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from konpy.cli._hook_findings import HookFinding
from konpy.cli._hook_rules import (
    build_rules_hook_prompt,
    normalize_rules_verdict,
    parse_rules_verdict,
)
from konpy.cli._hook_support import HookPayload
from konpy.cli._semantic_rules import SemanticRuleV1
from konpy.cli.agent_runner import AgentInvocation, AgentRunResult
from konpy.config.errors import Err, Result

type RunVerifier = Callable[[str], AgentRunResult]
type AppendFinding = Callable[[str | Path, HookFinding], Result[None]]
type WriteError = Callable[[str], None]


def run_rules_verifications(
    *,
    batches: Sequence[tuple[str, list[SemanticRuleV1]]],
    payload: HookPayload,
    invocation: AgentInvocation,
    agent_value: str,
    model: str,
    log_path: str | None,
    run_verifier: RunVerifier,
    append_finding: AppendFinding,
    write_error: WriteError,
) -> int:
    """Run one batched semantic verifier per applicable file."""
    for path, rules in batches:
        run_result = run_verifier(
            build_rules_hook_prompt(
                file_path=path,
                cwd=payload.cwd or "",
                rules=rules,
            )
        )
        if _agent_run_failed(invocation, run_result, write_error):
            return 1

        verdict = parse_rules_verdict(run_result.stdout)
        if verdict is None:
            write_error(
                f'Agent CLI "{invocation.agent}" did not return a valid verdict.'
            )
            return 1

        normalized = normalize_rules_verdict(
            verdict,
            applicable_rules=rules,
            file_path=path,
        )
        if isinstance(normalized, Err):
            write_error(
                f'Agent CLI "{invocation.agent}" returned an invalid verdict: '
                f"{normalized.error}"
            )
            return 1
        if not normalized.value:
            continue

        warnings: list[str] = []
        for failure in normalized.value:
            rule = failure["rule"]
            reasons = failure["reasons"]
            for reason in reasons:
                write_error(f"{rule.name}: {reason}")

            if log_path is not None:
                result = append_finding(
                    log_path,
                    HookFinding(
                        loggedAt=datetime.now(UTC).isoformat(),
                        sessionId=payload.session_id,
                        cwd=payload.cwd,
                        toolName=payload.tool_name,
                        filePath=path,
                        prompt=rule.prompt,
                        rule=rule.name,
                        agent=agent_value,
                        model=model,
                        reasons=reasons,
                    ),
                )
                if isinstance(result, Err):
                    warnings.append(result.error)

        for warning in warnings:
            write_error(f"konpy hook: --log warning: {warning}")
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


__all__ = ["run_rules_verifications"]
