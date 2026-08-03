"""Deterministic verification-step engine backing `konpy verify`.

Ports `scripts/verify`'s `Step`/`StepResult`/`_execute_step`/`_run_steps`
machinery onto a config-declared roster (the `verify` section of
`konpy.json`) instead of a hard-coded step table. Presentation-free: no
printing happens here -- `konpy.cli.verify` renders results and owns the
process exit code. See `docs/reference/cli.md#verify` for the user-facing
contract.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

Runner = Callable[..., subprocess.CompletedProcess[str]]

DEFAULT_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class VerifyStep:
    """One roster step: a name, the argv that runs it, and its timeout."""

    name: str
    argv: tuple[str, ...]
    timeout: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class VerifyStepResult:
    """The outcome of running one `VerifyStep`."""

    name: str
    ok: bool
    duration: float
    message: str | None = None


OnResult = Callable[[VerifyStepResult], None]


def execute_step(
    step: VerifyStep,
    *,
    cwd: Path,
    env: Mapping[str, str],
    runner: Runner = subprocess.run,
) -> VerifyStepResult:
    """Run one step, translating a missing executable or a timeout into a failure.

    Never raises for either condition: a step that could not run at all is
    reported as a `VerifyStepResult` with `ok=False`, the same as a step that
    ran and returned nonzero -- a deterministic gate must never let "did not
    run" read as "passed".
    """
    start = time.monotonic()
    try:
        completed = runner(
            list(step.argv), cwd=cwd, env=dict(env), timeout=step.timeout, check=False
        )
    except FileNotFoundError as error:
        return VerifyStepResult(
            name=step.name,
            ok=False,
            duration=time.monotonic() - start,
            message=(
                f"executable not found: {error} -- fix this step's `run` command "
                'under `"verify".steps` in konpy.json'
            ),
        )
    except subprocess.TimeoutExpired:
        return VerifyStepResult(
            name=step.name,
            ok=False,
            duration=time.monotonic() - start,
            message=f"timed out after {step.timeout}s",
        )

    ok = completed.returncode == 0
    return VerifyStepResult(
        name=step.name,
        ok=ok,
        duration=time.monotonic() - start,
        message=None if ok else f"exit code {completed.returncode}",
    )


def run_verify_steps(
    steps: Sequence[VerifyStep],
    *,
    cwd: Path,
    env: Mapping[str, str],
    runner: Runner = subprocess.run,
    on_result: OnResult | None = None,
) -> list[VerifyStepResult]:
    """Run every step in order, never stopping early, returning all results.

    `on_result`, if given, is invoked once per step immediately after it
    finishes, before the next step starts -- the CLI uses this to stream a
    `[verify] <name> ... ok|FAILED` line per step as the roster runs instead
    of buffering output until the whole roster completes.
    """
    results: list[VerifyStepResult] = []
    for step in steps:
        result = execute_step(step, cwd=cwd, env=env, runner=runner)
        if on_result is not None:
            on_result(result)
        results.append(result)
    return results


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "OnResult",
    "Runner",
    "VerifyStep",
    "VerifyStepResult",
    "execute_step",
    "run_verify_steps",
]
