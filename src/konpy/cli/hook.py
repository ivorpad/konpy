from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from datetime import UTC, datetime

from pydantic import ValidationError

from konpy.cli._hook_findings import HookFinding, append_hook_finding
from konpy.cli._hook_support import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOLS,
    HookAgent,
    HookPayload,
    Verdict,
    build_hook_prompt,
    extract_target_paths,
    hook_child_args,
    parse_verdict,
    path_matches_any,
)
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
) -> int:
    """Run the `konpy hook` PostToolUse verification flow.

    Reads the hook JSON payload from stdin (or `stdin_text`), skips fast for
    non-matching tools/paths or an active recursion sentinel, and otherwise
    invokes a read-only verifier agent per matched file, translating its
    verdict into the hook exit-code contract: 0 pass/skip, 2 fail, 1 infra
    fail-open.
    """
    active_env = env if env is not None else os.environ
    if active_env.get(SENTINEL_ENV):
        return 0

    # `--prompt`/`--agent` are logically required, but that requiredness is
    # enforced here (exit 1) rather than via Click's own required/choice
    # validation, which would exit 2 -- a code reserved exclusively for a
    # verified fail verdict. This must happen before anything else so that a
    # misconfigured hook command fails open uniformly, on every invocation.
    if not prompt:
        _write_error("Missing required --prompt for konpy hook.")
        return 1

    agent_value_result = _normalize_hook_agent(agent)
    if isinstance(agent_value_result, Err):
        _write_error(agent_value_result.error)
        return 1
    agent_value = agent_value_result.value

    raw_stdin = stdin_text if stdin_text is not None else sys.stdin.read()
    payload = _parse_payload(raw_stdin)
    if payload is None:
        return 0

    if payload.tool_name not in (CLAUDE_WRITE_TOOLS | CODEX_WRITE_TOOLS):
        return 0

    target_paths = extract_target_paths(payload)
    if not target_paths:
        return 0

    matched_paths = [path for path in target_paths if path_matches_any(path, match)]
    if not matched_paths:
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

    for path in matched_paths:
        hook_prompt = build_hook_prompt(
            file_path=path,
            cwd=payload.cwd or "",
            user_prompt=prompt,
        )
        run_result = _run_hook_agent(
            invocation=invocation,
            prompt=hook_prompt,
            runner=runner,
            model=model,
            timeout=timeout,
            agent_value=agent_value,
        )

        if run_result.returncode != 0:
            _write_error(
                f'Agent CLI "{invocation.agent}" exited with code {run_result.returncode}.'
            )
            if run_result.stderr.strip():
                _write_error(run_result.stderr.strip())
            elif run_result.stdout.strip():
                _write_error(run_result.stdout.strip())
            return 1

        verdict = parse_verdict(run_result.stdout)
        if verdict is None:
            _write_error(
                f'Agent CLI "{invocation.agent}" did not return a valid verdict.'
            )
            return 1

        if verdict["verdict"] == "fail":
            reasons = verdict["reasons"] or [f"Verification failed for {path}."]
            for reason in reasons:
                _write_error(reason)
            if log_path is not None:
                append_result = append_hook_finding(
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
                if isinstance(append_result, Err):
                    _write_error(
                        f"konpy hook: --log warning: {append_result.error}"
                    )
            return 2

    return 0


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

    child_env = {**os.environ, SENTINEL_ENV: "1"}
    return run_agent_subprocess(
        invocation=invocation,
        prompt=prompt,
        timeout=timeout,
        env=child_env,
        extra_args=hook_child_args(agent_value),
        model=model,
    )


def _parse_payload(raw: str) -> HookPayload | None:
    text = raw.strip()
    if not text:
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    try:
        return HookPayload.model_validate(data)
    except ValidationError:
        return None


def _normalize_hook_agent(agent: HookAgent | str | None) -> Result[str]:
    if agent is None or agent == "":
        return Err("Missing required --agent for konpy hook.")

    value = agent.value if isinstance(agent, HookAgent) else str(agent)
    if value in {HookAgent.CLAUDE.value, HookAgent.CODEX.value}:
        return Ok(value)

    return Err(f'Invalid agent "{value}". Expected one of: claude, codex.')


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
    "Verdict",
    "build_hook_prompt",
    "extract_target_paths",
    "hook_child_args",
    "parse_verdict",
    "path_matches_any",
    "run_hook_command",
]
