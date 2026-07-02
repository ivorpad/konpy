from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from wcmatch import glob as wcglob

from konsistent.cli.agent_runner import (
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    _test_invocation_for_runner,
    first_json_object,
    run_agent_subprocess,
    select_agent_invocation,
)
from konsistent.config.errors import Err, Ok, Result

_GLOB_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR

SENTINEL_ENV = "KONSISTENT_HOOK_ACTIVE"
DEFAULT_TIMEOUT = 300.0

CLAUDE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
CODEX_WRITE_TOOLS = {"apply_patch"}

_APPLY_PATCH_ENVELOPE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_UNIFIED_DIFF_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_CODEX_PATH_KEYS = ("file_path", "path")
_CODEX_SCAN_KEYS = ("input", "patch", "changes", "content", "diff")


class HookAgent(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"


class HookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None
    cwd: str | None = None
    hook_event_name: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_response: Any | None = None


class Verdict(TypedDict):
    verdict: Literal["pass", "fail"]
    reasons: list[str]


def run_hook_command(
    *,
    match: list[str],
    prompt: str | None,
    agent: HookAgent | str | None,
    timeout: float = DEFAULT_TIMEOUT,
    stdin_text: str | None = None,
    runner: AgentRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    active_env = env if env is not None else os.environ
    if active_env.get(SENTINEL_ENV):
        return 0

    # `--prompt`/`--agent` are logically required, but that requiredness is
    # enforced here (exit 1) rather than via Click's own required/choice
    # validation, which would exit 2 -- a code reserved exclusively for a
    # verified fail verdict. This must happen before anything else so that a
    # misconfigured hook command fails open uniformly, on every invocation.
    if not prompt:
        _write_error("Missing required --prompt for konsistent hook.")
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
            return 2

    return 0


def extract_target_paths(payload: HookPayload) -> list[str]:
    if payload.tool_name in CLAUDE_WRITE_TOOLS:
        raw = payload.tool_input.get("file_path")
        if isinstance(raw, str) and raw:
            return [_normalize_target_path(raw, cwd=payload.cwd)]
        return []

    if payload.tool_name in CODEX_WRITE_TOOLS:
        return _extract_codex_paths(payload)

    return []


def path_matches_any(path: str, patterns: Sequence[str]) -> bool:
    normalized = path.replace(os.sep, "/")
    return wcglob.globmatch(normalized, list(patterns), flags=_GLOB_FLAGS)


def build_hook_prompt(*, file_path: str, cwd: str, user_prompt: str) -> str:
    return f"""\
You are a read-only verification agent invoked from a konsistent PostToolUse hook.

Working directory: {cwd}
File to inspect (read-only; do not modify): {file_path}

Verification instruction:
{user_prompt}

Read the file yourself using your available read-only tools. If the file is
unreadable, missing, or the instruction does not apply, treat the result as a
pass.

Return exactly one JSON object with this contract and nothing else:

{{"verdict": "pass" | "fail", "reasons": ["..."]}}

"reasons" must be empty when the verdict is "pass" and must contain concrete,
actionable feedback when the verdict is "fail" — it will be shown directly to
the coding agent that wrote the file so it can self-correct.
"""


def parse_verdict(stdout: str) -> Verdict | None:
    candidate = first_json_object(
        stdout, predicate=lambda obj: obj.get("verdict") in {"pass", "fail"}
    )
    if candidate is None:
        return None

    verdict = candidate.get("verdict")
    if verdict not in {"pass", "fail"}:
        return None

    reasons = candidate.get("reasons", [])
    if reasons is None:
        reasons = []
    if not isinstance(reasons, list):
        return None

    return {"verdict": verdict, "reasons": [str(reason) for reason in reasons]}


def hook_child_args(agent: HookAgent | str) -> tuple[str, ...]:
    value = agent.value if isinstance(agent, HookAgent) else str(agent)
    if value == HookAgent.CLAUDE.value:
        return ("--allowedTools", "Read", "Grep", "Glob", "--settings", '{"hooks":{}}')
    if value == HookAgent.CODEX.value:
        return ("--sandbox", "read-only")
    return ()


def _run_hook_agent(
    *,
    invocation: AgentInvocation,
    prompt: str,
    runner: AgentRunner | None,
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
        return Err("Missing required --agent for konsistent hook.")

    value = agent.value if isinstance(agent, HookAgent) else str(agent)
    if value in {HookAgent.CLAUDE.value, HookAgent.CODEX.value}:
        return Ok(value)

    return Err(f'Invalid agent "{value}". Expected one of: claude, codex.')


def _normalize_target_path(raw: str, *, cwd: str | None) -> str:
    path = Path(raw)
    if cwd and path.is_absolute():
        with contextlib.suppress(ValueError):
            path = path.relative_to(Path(cwd))
    return str(path).replace(os.sep, "/")


def _extract_codex_paths(payload: HookPayload) -> list[str]:
    tool_input = payload.tool_input

    for key in _CODEX_PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return [_normalize_target_path(value, cwd=payload.cwd)]

    for key in _CODEX_SCAN_KEYS:
        value = tool_input.get(key)
        if not isinstance(value, str):
            continue

        matches = _APPLY_PATCH_ENVELOPE_RE.findall(value) or _UNIFIED_DIFF_RE.findall(value)
        if matches:
            return [_normalize_target_path(match.strip(), cwd=payload.cwd) for match in matches]

    return []


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = [
    "CLAUDE_WRITE_TOOLS",
    "CODEX_WRITE_TOOLS",
    "DEFAULT_TIMEOUT",
    "SENTINEL_ENV",
    "HookAgent",
    "HookPayload",
    "Verdict",
    "build_hook_prompt",
    "extract_target_paths",
    "hook_child_args",
    "parse_verdict",
    "path_matches_any",
    "run_hook_command",
]
