from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from konsistent.config.errors import Err, Ok, Result


class ExtractAgent(StrEnum):
    """Agent CLI selection for `konsistent extract-rules`: auto-detect, claude, or codex."""

    AUTO = "auto"
    CLAUDE = "claude"
    CODEX = "codex"


@dataclass(frozen=True)
class AgentInvocation:
    """A resolved agent CLI: which binary to run and its fixed prefix args."""

    agent: str
    executable: str
    prefix_args: tuple[str, ...]


@dataclass(frozen=True)
class AgentRunResult:
    """The outcome of running an agent CLI subprocess."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


type AgentRunner = Callable[[AgentInvocation, str], AgentRunResult | str]

AGENT_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "claude": ("claude", ("-p",)),
    "codex": ("codex", ("exec",)),
}

DEFAULT_MODEL = "sonnet"

_FENCE_RE = re.compile(r"```(?:json|JSON)?[^\n]*\n(?P<body>.*?)```", re.DOTALL)


def select_agent_invocation(agent: ExtractAgent | str) -> Result[AgentInvocation]:
    """Resolve an agent choice to a concrete `AgentInvocation` on PATH.

    For `auto`, tries `claude` then `codex`, returning the first found.
    """
    agent_value_result = _normalize_agent(agent)
    if isinstance(agent_value_result, Err):
        return agent_value_result
    agent_value = agent_value_result.value

    if agent_value == ExtractAgent.AUTO.value:
        for candidate in (ExtractAgent.CLAUDE.value, ExtractAgent.CODEX.value):
            executable = shutil.which(candidate)
            if executable is not None:
                return Ok(_invocation_for(agent=candidate, executable=executable))

        return Err("No supported agent CLI found on PATH. Install one of: claude, codex.")

    executable = shutil.which(agent_value)
    if executable is None:
        return Err(f'Agent CLI "{agent_value}" not found on PATH.')

    return Ok(_invocation_for(agent=agent_value, executable=executable))


def iter_json_objects(text: str) -> Iterator[dict[str, object]]:
    """Yield each top-level JSON object decodable from `text`, brace by brace."""
    decoder = json.JSONDecoder()
    stripped = text.strip().lstrip("﻿")

    for index, char in enumerate(stripped):
        if char != "{":
            continue

        try:
            decoded, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(decoded, dict):
            yield decoded


def first_json_object(
    text: str,
    *,
    predicate: Callable[[dict[str, object]], bool] | None = None,
) -> dict[str, object] | None:
    """Return the first JSON object in `text` (fenced or bare) matching `predicate`.

    Without a `predicate`, returns the first object found. Used to skip
    incidental JSON-shaped text before the real response object.
    """
    candidates: list[dict[str, object]] = []

    for match in _FENCE_RE.finditer(text.strip()):
        candidates.extend(iter_json_objects(match.group("body")))

    candidates.extend(iter_json_objects(text))

    if predicate is not None:
        for candidate in candidates:
            if predicate(candidate):
                return candidate

    if candidates:
        return candidates[0]

    return None


def run_agent_subprocess(
    *,
    invocation: AgentInvocation,
    prompt: str,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    extra_args: Sequence[str] = (),
    model: str | None = None,
) -> AgentRunResult:
    """Run the agent CLI as a subprocess with `prompt` as its final argument.

    Captures stdout/stderr and turns a timeout or missing executable into an
    `AgentRunResult` rather than letting the exception propagate.
    """
    model_args = ("--model", model) if model else ()
    command = [
        invocation.executable,
        *invocation.prefix_args,
        *model_args,
        *extra_args,
        prompt,
    ]

    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return AgentRunResult(
            returncode=124,
            stdout="",
            stderr=f'Agent CLI "{invocation.agent}" timed out after {timeout}s.',
            timed_out=True,
        )
    except OSError as error:
        return AgentRunResult(
            returncode=127,
            stdout="",
            stderr=f'Could not start agent CLI "{invocation.agent}": {error}',
        )

    return AgentRunResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _normalize_agent(agent: ExtractAgent | str) -> Result[str]:
    value = agent.value if isinstance(agent, ExtractAgent) else str(agent)
    if value in {
        ExtractAgent.AUTO.value,
        ExtractAgent.CLAUDE.value,
        ExtractAgent.CODEX.value,
    }:
        return Ok(value)

    return Err(f'Invalid agent "{value}". Expected one of: auto, claude, codex.')


def _test_invocation_for_runner(agent: str) -> Result[AgentInvocation]:
    selected = ExtractAgent.CLAUDE.value if agent == ExtractAgent.AUTO.value else agent
    return Ok(_invocation_for(agent=selected, executable=selected))


def _invocation_for(*, agent: str, executable: str) -> AgentInvocation:
    _binary, prefix_args = AGENT_COMMANDS[agent]
    return AgentInvocation(agent=agent, executable=executable, prefix_args=prefix_args)


__all__ = [
    "AGENT_COMMANDS",
    "DEFAULT_MODEL",
    "AgentInvocation",
    "AgentRunResult",
    "AgentRunner",
    "ExtractAgent",
    "first_json_object",
    "iter_json_objects",
    "run_agent_subprocess",
    "select_agent_invocation",
]
