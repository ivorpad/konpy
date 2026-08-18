"""`konpy improve`: propose a human-reviewable diff for one duplication finding.

Runs a read-only agent over the top-ranked (or explicitly selected)
duplicate-function group from the zero-config report's duplication lane and
asks it for a unified diff plus a short rationale. konpy never parses,
applies, or validates the diff beyond a non-empty, diff-shaped sanity check
-- review and application are entirely up to the human on the other end.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from konpy.cli._improve_prompt import build_improve_prompt
from konpy.cli.agent_runner import (
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    ExtractAgent,
    _test_invocation_for_runner,
    run_agent,
    select_agent_invocation,
    write_agent_failure,
)
from konpy.cli.agent_runner import (
    _normalize_agent as _normalize_agent_value,
)
from konpy.cli.hook import SENTINEL_ENV, hook_child_args
from konpy.config.errors import Err, Result
from konpy.core._improve_groups import collect_duplicate_function_groups, select_group
from konpy.core.filesystem import RealFileSystem

DEFAULT_TIMEOUT = 300.0

_DIFF_LINE_PREFIXES = ("--- ", "diff ")


def run_improve_command(
    *,
    group_name: str | None = None,
    agent: ExtractAgent | str = ExtractAgent.AUTO,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT,
    output_path: str | None = None,
    config_path: str | None = None,
    runner: AgentRunner | None = None,
) -> int:
    """Propose a reviewable diff for one duplicate-function finding.

    Never touches any file on disk except `output_path`. `config_path` only
    anchors the scan root (mirroring `check`/`report`); no config needs to
    exist for group selection, which runs the same zero-config duplication
    scan `konpy report` renders.
    """
    agent_result = _normalize_agent_value(agent)
    if isinstance(agent_result, Err):
        _write_error(agent_result.error)
        return 1
    agent_value = agent_result.value

    root = Path(config_path).parent if config_path else Path.cwd()
    file_system = RealFileSystem(cwd=root)
    groups = collect_duplicate_function_groups(file_system, root=root)

    group_result = select_group(groups, group_name)
    if isinstance(group_result, Err):
        _write_error(group_result.error)
        return 1
    group = group_result.value

    invocation_result: Result[AgentInvocation]
    if runner is None:
        invocation_result = select_agent_invocation(agent_value)
    else:
        invocation_result = _test_invocation_for_runner(agent_value)
    if isinstance(invocation_result, Err):
        _write_error(invocation_result.error)
        return 1
    invocation = invocation_result.value

    prompt = build_improve_prompt(group)
    _write_progress(
        f'proposing a fix for "{group.name}" ({len(group.members)} copies) '
        f'via "{invocation.agent}" --model {model} (typically takes a few '
        "minutes)..."
    )
    started = time.monotonic()
    run_result = run_agent(
        invocation=invocation,
        prompt=prompt,
        runner=runner,
        model=model,
        timeout=timeout,
        extra_args=hook_child_args(invocation.agent),
        env={**os.environ, SENTINEL_ENV: "1"},
    )
    _write_progress(f'agent "{invocation.agent}" finished in {time.monotonic() - started:.0f}s.')

    if run_result.returncode != 0:
        write_agent_failure(invocation, run_result, _write_error)
        return 1

    response = run_result.stdout
    if not _looks_like_diff(response):
        sys.stderr.write("konpy improve: agent did not produce a reviewable diff.\n")
        sys.stdout.write(response)
        return 1

    if output_path is not None:
        Path(output_path).write_text(response, encoding="utf-8")
        sys.stdout.write(f"Wrote proposed diff to {output_path}\n")
    else:
        sys.stdout.write(response)
    return 0


def _looks_like_diff(text: str) -> bool:
    """A cheap diff-shaped sanity check -- never a real patch validation."""
    return any(line.startswith(_DIFF_LINE_PREFIXES) for line in text.splitlines())


def _write_progress(message: str) -> None:
    sys.stderr.write(f"konpy improve: {message}\n")


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["DEFAULT_TIMEOUT", "run_improve_command"]
