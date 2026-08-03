"""`konpy review`: advisory PostToolUse verification that never fails.

A model verdict is not authoritative here: findings are reported, never
enforced. Only `konpy gate` (a deterministic PreToolUse check) may block a
proposed write before it lands; `konpy hook` stops at the first fail verdict
and exits 2 to feed an agent corrective stderr for a follow-up turn. `review`
does neither — it runs every matched path (or rule batch) to completion,
streams every fail reason to stderr as it goes, and additionally emits a
single Claude Code `additionalContext` JSON object on stdout summarizing all
findings — no exit code from this command is ever nonzero for a finding.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence

from konpy.cli._hook_findings import append_hook_finding
from konpy.cli._hook_prompt_run import run_prompt_verifications
from konpy.cli._hook_rules_run import run_rules_verifications
from konpy.cli._hook_shared import resolve_hook_target
from konpy.cli._review_outcome import ReviewFinding
from konpy.cli._semantic_rules import read_semantic_rules
from konpy.cli.agent_runner import (
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    _test_invocation_for_runner,
    select_agent_invocation,
)
from konpy.cli.hook import (
    DEFAULT_TIMEOUT,
    SENTINEL_ENV,
    HookAgent,
    _normalize_hook_agent,
    _run_hook_agent,
)
from konpy.config.errors import Err, Result


def run_review_command(
    *,
    match: list[str],
    prompt: str | None,
    rules_path: str | None,
    agent: HookAgent | str | None,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
    log_path: str | None = None,
    stdin_text: str | None = None,
    runner: AgentRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run advisory single-prompt or semantic-rules PostToolUse review.

    Every matched path (or applicable rule batch) is verified regardless of
    earlier failures, and every verified finding is logged/reported — there
    is no stop-on-first-failure short-circuit here, unlike `konpy hook`.
    A missing or misbehaving verifier agent degrades to a stderr warning
    rather than a nonzero exit: an advisory check must not fail a write just
    because a model was unavailable. The only paths that exit nonzero are
    local misconfiguration (bad flags, an unreadable/invalid rules file),
    which exit 1 exactly like `konpy hook` does for the same conditions.
    """
    active_env = env if env is not None else os.environ
    if active_env.get(SENTINEL_ENV):
        return 0

    if prompt and rules_path:
        _write_error("--prompt and --rules are mutually exclusive for konpy review.")
        return 1
    if not prompt and not rules_path:
        _write_error(
            "Exactly one of --prompt or --rules is required for konpy review."
        )
        return 1

    agent_result = _normalize_hook_agent(agent)
    if isinstance(agent_result, Err):
        _write_error(agent_result.error)
        return 1
    agent_value = agent_result.value

    rules_package = None
    if rules_path:
        rules_result = read_semantic_rules(rules_path)
        if isinstance(rules_result, Err):
            _write_error(rules_result.error)
            return 1
        rules_package = rules_result.value

    raw_stdin = stdin_text if stdin_text is not None else sys.stdin.read()
    target = resolve_hook_target(
        raw_stdin=raw_stdin,
        match=match,
        rules_package=rules_package,
    )
    if target is None:
        return 0
    payload = target.payload
    matched_paths = target.matched_paths
    batches = target.batches

    invocation_result: Result[AgentInvocation]
    if runner is None:
        invocation_result = select_agent_invocation(agent_value)
    else:
        invocation_result = _test_invocation_for_runner(agent_value)
    if isinstance(invocation_result, Err):
        _write_warning(invocation_result.error)
        return 0
    invocation = invocation_result.value

    def run_verifier(verifier_prompt: str) -> AgentRunResult:
        return _run_hook_agent(
            invocation=invocation,
            prompt=verifier_prompt,
            runner=runner,
            model=model,
            timeout=timeout,
            agent_value=agent_value,
        )

    if rules_package is None:
        outcome = run_prompt_verifications(
            paths=matched_paths,
            prompt=prompt or "",
            payload=payload,
            invocation=invocation,
            agent_value=agent_value,
            model=model,
            log_path=log_path,
            run_verifier=run_verifier,
            append_finding=append_hook_finding,
            write_error=_write_error,
            stop_on_first_failure=False,
            command_name="review",
        )
    else:
        outcome = run_rules_verifications(
            batches=batches,
            payload=payload,
            invocation=invocation,
            agent_value=agent_value,
            model=model,
            log_path=log_path,
            run_verifier=run_verifier,
            append_finding=append_hook_finding,
            write_error=_write_error,
            stop_on_first_failure=False,
            command_name="review",
        )

    if outcome.status == "findings":
        sys.stdout.write(_render_additional_context(outcome.findings))
        sys.stdout.write("\n")

    return 0


def _render_additional_context(findings: Sequence[ReviewFinding]) -> str:
    """Render findings as one PostToolUse `additionalContext` JSON object."""
    lines = ["konpy review findings:"]
    for finding in findings:
        prefix = f"{finding.rule}: " if finding.rule else ""
        reason_text = "; ".join(finding.reasons)
        lines.append(f"{finding.path}: {prefix}{reason_text}")

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(lines),
        }
    }
    return json.dumps(payload)


def _write_warning(message: str) -> None:
    sys.stderr.write(f"konpy review: warning: {message}\n")


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["run_review_command"]
