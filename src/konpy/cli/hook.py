from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

from konpy.cli._hook_findings import HookFinding, append_hook_finding
from konpy.cli._hook_prompt_run import run_prompt_verifications
from konpy.cli._hook_rules_run import run_rules_verifications
from konpy.cli._hook_support import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOLS,
    HookAgent,
    HookPayload,
    RuleFailure,
    RulesVerdict,
    Verdict,
    build_hook_prompt,
    build_rules_hook_prompt,
    extract_target_paths,
    hook_child_args,
    parse_hook_payload,
    parse_rules_verdict,
    parse_verdict,
    path_matches_any,
)
from konpy.cli._semantic_rules import SemanticRuleV1, read_semantic_rules
from konpy.cli.agent_runner import (
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    _test_invocation_for_runner,
    run_agent_subprocess,
    select_agent_invocation,
)
from konpy.config.errors import Err, Ok, Result

SENTINEL_ENV = "KONPY_HOOK_ACTIVE"
DEFAULT_TIMEOUT = 300.0


def run_hook_command(
    *,
    match: list[str],
    prompt: str | None,
    agent: HookAgent | str | None,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
    log_path: str | None = None,
    stdin_text: str | None = None,
    runner: AgentRunner | None = None,
    env: Mapping[str, str] | None = None,
    rules_path: str | None = None,
) -> int:
    """Run single-prompt or semantic-rules PostToolUse verification."""
    active_env = env if env is not None else os.environ
    if active_env.get(SENTINEL_ENV):
        return 0

    if prompt and rules_path:
        _write_error("--prompt and --rules are mutually exclusive for konpy hook.")
        return 1
    if not prompt and not rules_path:
        _write_error(
            "Exactly one of --prompt or --rules is required for konpy hook."
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
    payload = parse_hook_payload(raw_stdin)
    if payload is None:
        return 0
    if payload.tool_name not in (CLAUDE_WRITE_TOOLS | CODEX_WRITE_TOOLS):
        return 0

    target_paths = extract_target_paths(payload)
    matched_paths = [
        path for path in target_paths if path_matches_any(path, match)
    ]
    if not matched_paths:
        return 0

    batches: list[tuple[str, list[SemanticRuleV1]]] = []
    if rules_package is not None:
        for path in _dedupe_paths(matched_paths):
            applicable = [
                rule
                for rule in rules_package.rules
                if path_matches_any(path, rule.match)
            ]
            if applicable:
                batches.append((path, applicable))
        if not batches:
            return 0

    invocation_result: Result[AgentInvocation]
    if runner is None:
        invocation_result = select_agent_invocation(agent_value)
    else:
        invocation_result = _test_invocation_for_runner(agent_value)
    if isinstance(invocation_result, Err):
        _write_error(invocation_result.error)
        return 1
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
        return run_prompt_verifications(
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
        )

    return run_rules_verifications(
        batches=batches,
        payload=payload,
        invocation=invocation,
        agent_value=agent_value,
        model=model,
        log_path=log_path,
        run_verifier=run_verifier,
        append_finding=append_hook_finding,
        write_error=_write_error,
    )


def _run_hook_agent(
    *,
    invocation: AgentInvocation,
    prompt: str,
    runner: AgentRunner | None,
    model: str,
    timeout: float,
    agent_value: str,
) -> AgentRunResult:
    if runner is not None:
        result = runner(invocation, prompt)
        if isinstance(result, AgentRunResult):
            return result
        return AgentRunResult(returncode=0, stdout=result, stderr="")

    return run_agent_subprocess(
        invocation=invocation,
        prompt=prompt,
        timeout=timeout,
        env={**os.environ, SENTINEL_ENV: "1"},
        extra_args=hook_child_args(agent_value),
        model=model,
    )


def _normalize_hook_agent(agent: HookAgent | str | None) -> Result[str]:
    if agent is None or agent == "":
        return Err("Missing required --agent for konpy hook.")

    value = agent.value if isinstance(agent, HookAgent) else str(agent)
    if value in {HookAgent.CLAUDE.value, HookAgent.CODEX.value}:
        return Ok(value)
    return Err(f'Invalid agent "{value}". Expected one of: claude, codex.')


def _dedupe_paths(paths: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(paths))


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = [
    "CLAUDE_WRITE_TOOLS",
    "CODEX_WRITE_TOOLS",
    "DEFAULT_TIMEOUT",
    "SENTINEL_ENV",
    "HookAgent",
    "HookFinding",
    "HookPayload",
    "RuleFailure",
    "RulesVerdict",
    "Verdict",
    "build_hook_prompt",
    "build_rules_hook_prompt",
    "extract_target_paths",
    "hook_child_args",
    "parse_rules_verdict",
    "parse_verdict",
    "path_matches_any",
    "run_hook_command",
]
