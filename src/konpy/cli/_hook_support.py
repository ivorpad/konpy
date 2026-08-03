"""Payload, path, prompt, and verdict helpers for `konpy hook`."""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from wcmatch import glob as wcglob

from konpy.cli._hook_rules import (
    NormalizedRuleFailure,
    RuleFailure,
    RulesVerdict,
    build_rules_hook_prompt,
    normalize_rules_verdict,
    parse_rules_verdict,
)
from konpy.cli.agent_runner import first_json_object

_GLOB_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR

CLAUDE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
CODEX_WRITE_TOOLS = {"apply_patch"}

_APPLY_PATCH_ENVELOPE_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+)$",
    re.MULTILINE,
)
_UNIFIED_DIFF_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_CODEX_PATH_KEYS = ("file_path", "path")
_CODEX_SCAN_KEYS = ("input", "patch", "changes", "content", "diff")


class HookAgent(StrEnum):
    """Verifier agent CLI selectable for `konpy hook`."""

    CLAUDE = "claude"
    CODEX = "codex"


class HookPayload(BaseModel):
    """Parsed subset of a Claude Code/Codex PostToolUse payload."""

    model_config = ConfigDict(extra="ignore")

    session_id: str | None = None
    cwd: str | None = None
    hook_event_name: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, object] = Field(default_factory=dict)
    tool_response: object | None = None


class Verdict(TypedDict):
    """Normalized single-prompt verifier verdict."""

    verdict: Literal["pass", "fail"]
    reasons: list[str]


def parse_hook_payload(raw: str) -> HookPayload | None:
    """Parse a hook JSON payload, returning None for non-payloads."""
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


def extract_target_paths(payload: HookPayload) -> list[str]:
    """Return the file paths targeted by a supported write tool."""
    if payload.tool_name in CLAUDE_WRITE_TOOLS:
        raw = payload.tool_input.get("file_path")
        if isinstance(raw, str) and raw:
            return [_normalize_target_path(raw, cwd=payload.cwd)]
        return []

    if payload.tool_name in CODEX_WRITE_TOOLS:
        return _extract_codex_paths(payload)
    return []


def path_matches_any(path: str, patterns: Sequence[str]) -> bool:
    """Check whether `path` matches any supplied glob."""
    normalized = path.replace(os.sep, "/")
    return wcglob.globmatch(normalized, list(patterns), flags=_GLOB_FLAGS)


def build_hook_prompt(*, file_path: str, cwd: str, user_prompt: str) -> str:
    """Build the existing single-instruction verification prompt."""
    return f"""\
You are a read-only verification agent invoked from a konpy PostToolUse hook.

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
    """Parse the existing single-prompt verifier verdict."""
    candidate = first_json_object(
        stdout,
        predicate=lambda obj: obj.get("verdict") in {"pass", "fail"},
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

    reason_list = [str(reason) for reason in reasons]
    if verdict == "pass":
        return {"verdict": "pass", "reasons": reason_list}
    return {"verdict": "fail", "reasons": reason_list}


def hook_child_args(agent: HookAgent | str) -> tuple[str, ...]:
    """Return read-only CLI arguments for the verifier agent."""
    value = agent.value if isinstance(agent, HookAgent) else str(agent)
    if value == HookAgent.CLAUDE.value:
        return (
            "--allowedTools",
            "Read",
            "Grep",
            "Glob",
            "--settings",
            '{"hooks":{}}',
        )
    if value == HookAgent.CODEX.value:
        return ("--sandbox", "read-only")
    return ()


def _normalize_target_path(raw: str, *, cwd: str | None) -> str:
    path = Path(raw)
    if cwd and path.is_absolute():
        with contextlib.suppress(ValueError):
            path = path.relative_to(Path(cwd))
    return str(path).replace(os.sep, "/")


def _extract_codex_paths(payload: HookPayload) -> list[str]:
    for key in _CODEX_PATH_KEYS:
        value = payload.tool_input.get(key)
        if isinstance(value, str) and value:
            return [_normalize_target_path(value, cwd=payload.cwd)]

    for key in _CODEX_SCAN_KEYS:
        value = payload.tool_input.get(key)
        if not isinstance(value, str):
            continue
        matches = (
            _APPLY_PATCH_ENVELOPE_RE.findall(value)
            or _UNIFIED_DIFF_RE.findall(value)
        )
        if matches:
            return [
                _normalize_target_path(match.strip(), cwd=payload.cwd)
                for match in matches
            ]
    return []


__all__ = [
    "CLAUDE_WRITE_TOOLS",
    "CODEX_WRITE_TOOLS",
    "HookAgent",
    "HookPayload",
    "NormalizedRuleFailure",
    "RuleFailure",
    "RulesVerdict",
    "Verdict",
    "build_hook_prompt",
    "build_rules_hook_prompt",
    "extract_target_paths",
    "hook_child_args",
    "normalize_rules_verdict",
    "parse_hook_payload",
    "parse_rules_verdict",
    "parse_verdict",
    "path_matches_any",
]
