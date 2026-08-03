"""`konpy verify`: run a config-declared roster of verification steps.

Ports `scripts/verify`'s step-runner semantics onto a `konpy.json`-declared
roster (the `verify` section) instead of a hard-coded step table, so a repo
can define its own CI/pre-commit/agent-hook entry point without a bespoke
script. See `konpy.core.verify` for the engine and
`docs/reference/cli.md#verify` for the full command reference.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from konpy.config.errors import Err
from konpy.config.loader import CONFIG_FILENAME, load_config_runtime
from konpy.core.verify import VerifyStep, VerifyStepResult, run_verify_steps

__all__ = ["run_verify_command"]


def run_verify_command(*, config_path: str | None) -> int:
    """Run the `verify` roster declared in the resolved config.

    Loads the config the same way `check`/`explain` do -- `extends`,
    `disable`, `plugins`, `conventionSources`, the works -- so a missing or
    invalid `konpy.json` errors identically. A config with no `verify`
    section is not silently a no-op: it prints one pointer message and exits
    `1`. Otherwise every declared step always runs, in order, from the
    resolved config file's directory (so the roster is repo-root-relative
    regardless of the caller's own cwd), with the caller's environment plus
    `KONPY_VERIFY_ACTIVE=1`. A missing executable or a timed-out step is a
    step FAILURE, never a skip -- see `konpy.core.verify.execute_step`.
    """
    config_display_path = (
        Path(config_path) if config_path is not None else Path.cwd() / CONFIG_FILENAME
    )

    loaded_result = load_config_runtime(config_path=config_path)
    if isinstance(loaded_result, Err):
        _write_error(loaded_result.error)
        return 1

    verify_config = loaded_result.value.config.verify
    if verify_config is None:
        _write_error(
            f'No verify section in {config_display_path}. Add "verify": '
            '{"steps": [...]} — see the verify section in "konpy docs cli".'
        )
        return 1

    steps = [
        VerifyStep(name=step.name, argv=tuple(step.run), timeout=step.timeout)
        for step in verify_config.steps
    ]
    env = {**os.environ, "KONPY_VERIFY_ACTIVE": "1"}

    results = run_verify_steps(
        steps,
        cwd=config_display_path.parent,
        env=env,
        on_result=_print_step_line,
    )

    failed = [result.name for result in results if not result.ok]
    if failed:
        _print_summary(failed)
        return 1
    return 0


def _print_step_line(result: VerifyStepResult) -> None:
    """Print the one-line `[verify] <name> ... ok|FAILED (Ns)` report for a step."""
    status = "ok" if result.ok else "FAILED"
    sys.stdout.write(f"[verify] {result.name} ... {status} ({result.duration:.2f}s)\n")
    if not result.ok and result.message:
        sys.stdout.write(f"[verify]   {result.message}\n")


def _print_summary(failed_names: Sequence[str]) -> None:
    """Print the end-of-run summary listing every failed step name."""
    sys.stdout.write(f"[verify] FAILED: {', '.join(failed_names)}\n")


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")
