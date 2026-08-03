"""PreToolUse deterministic gate for proposed Claude Code writes."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from konpy.cli._baseline_support import read_baseline_if_present, resolve_baseline_path
from konpy.cli._check_support import (
    has_errors,
    has_warnings,
    prepare_check_runtime,
)
from konpy.cli._gate_ruff import ruff_available, run_ruff_on_overlay
from konpy.cli._gate_support import reconstruct_proposed_content
from konpy.cli._hook_support import (
    CLAUDE_WRITE_TOOLS,
    extract_target_paths,
    parse_hook_payload,
    path_matches_any,
)
from konpy.cli.check import DiagnosticLevel
from konpy.config.errors import Err
from konpy.core.filesystem import FileSystem, OverlayFileSystem, RealFileSystem
from konpy.core.reporters import count_severities, format_json
from konpy.core.runner import RunResult, run
from konpy.core.truncate import truncate_diagnostics

__all__ = ["run_gate_command"]

_GateStatus = Literal["pass", "skip", "violation", "verification-unavailable"]


@dataclass(frozen=True, kw_only=True)
class _GateOutcome:
    """The result of evaluating a `konpy gate` payload, before exit-code mapping."""

    status: _GateStatus
    detail: str | None = None
    run_result: RunResult | None = None


def run_gate_command(
    *,
    match: list[str],
    config_path: str | None,
    config_package: str | None,
    diagnostic_level: DiagnosticLevel | str,
    error_on_warnings: bool,
    placeholder: list[str] | None,
    max_diagnostics: int,
    stdin_text: str | None = None,
    file_system: FileSystem | None = None,
    env: Mapping[str, str] | None = None,
    fail_closed: bool = False,
    baseline: str | None = None,
    ruff: bool = False,
) -> int:
    """Run the `konpy gate` PreToolUse flow.

    Exit 2 is reserved for verified convention violations in the proposed
    content and, in `fail_closed` mode, for payloads deterministic
    verification cannot run against at all. By default (`fail_closed=False`)
    payload skips, unreconstructable content, config errors, and runtime
    failures all fail open with exit 0.

    `ruff=True` additionally runs `ruff check` against the proposed content
    of every `.py` overlay target, using the target repo's own ruff config.
    Findings are reported as error-severity diagnostics under the `ruff`
    convention name and block the write like any other verified violation.
    A missing `ruff` executable follows the same fail-open/`fail_closed`
    contract as any other verification-unavailable case.
    """
    del env

    raw_stdin = stdin_text if stdin_text is not None else sys.stdin.read()

    outcome = _compute_gate_outcome(
        raw_stdin=raw_stdin,
        match=match,
        config_path=config_path,
        config_package=config_package,
        diagnostic_level=diagnostic_level,
        error_on_warnings=error_on_warnings,
        placeholder=placeholder,
        file_system=file_system,
        fail_closed=fail_closed,
        baseline=baseline,
        ruff=ruff,
    )

    return _exit_code_for_outcome(outcome, max_diagnostics=max_diagnostics)


def _compute_gate_outcome(
    *,
    raw_stdin: str,
    match: list[str],
    config_path: str | None,
    config_package: str | None,
    diagnostic_level: DiagnosticLevel | str,
    error_on_warnings: bool,
    placeholder: list[str] | None,
    file_system: FileSystem | None,
    fail_closed: bool,
    baseline: str | None,
    ruff: bool,
) -> _GateOutcome:
    """Evaluate a gate payload to one pass/skip/violation/verification-unavailable outcome."""
    payload = parse_hook_payload(raw_stdin)
    if payload is None:
        if fail_closed:
            return _GateOutcome(
                status="verification-unavailable",
                detail="unable to parse hook payload",
            )
        return _GateOutcome(status="skip")

    if payload.tool_name not in CLAUDE_WRITE_TOOLS:
        return _GateOutcome(status="skip")

    target_paths = extract_target_paths(payload)
    if not target_paths:
        if fail_closed:
            return _GateOutcome(
                status="verification-unavailable",
                detail=f"no target paths extracted from {payload.tool_name} payload",
            )
        return _GateOutcome(status="skip")

    matched_paths = [
        path for path in target_paths if not match or path_matches_any(path, match)
    ]
    if not matched_paths:
        return _GateOutcome(status="skip")

    try:
        # Filesystem construction stays inside the try so even a failing
        # Path.cwd() maps onto the fail-open/fail-closed contract.
        base = file_system if file_system is not None else RealFileSystem(cwd=Path.cwd())
        reconstructed = reconstruct_proposed_content(payload, base=base)
        overlay = (
            {path: content for path, content in reconstructed.items() if path in matched_paths}
            if reconstructed is not None
            else {}
        )
        if not overlay:
            if fail_closed:
                return _GateOutcome(
                    status="verification-unavailable",
                    detail="unable to reconstruct proposed content",
                )
            return _GateOutcome(status="skip")

        # Checked up front, before the (much more expensive) convention
        # check: if `--ruff` is set and there's a `.py` overlay target but no
        # `ruff` executable, verification can't run at all -- same
        # fail-open/fail-closed contract as every other case below.
        ruff_py_paths = [path for path in overlay if path.endswith(".py")]
        if ruff and ruff_py_paths and not ruff_available():
            detail = "ruff not found on PATH (required by --ruff)"
            if fail_closed:
                return _GateOutcome(status="verification-unavailable", detail=detail)
            return _GateOutcome(status="skip", detail=detail)

        prepared_result = prepare_check_runtime(
            config_path=config_path,
            config_package=config_package,
            diagnostic_level=diagnostic_level,
            placeholder=placeholder,
        )
        if isinstance(prepared_result, Err):
            status: _GateStatus = "verification-unavailable" if fail_closed else "skip"
            return _GateOutcome(status=status, detail=prepared_result.error)

        # Auto-discovered or explicit `--baseline`: pre-existing baselined
        # violations never block a proposed write, only NEW ones do. A
        # malformed baseline is treated exactly like a config-load failure.
        baseline_path = resolve_baseline_path(baseline=baseline, config_path=config_path)
        baseline_result = read_baseline_if_present(baseline_path)
        if isinstance(baseline_result, Err):
            status = "verification-unavailable" if fail_closed else "skip"
            return _GateOutcome(status=status, detail=baseline_result.error)

        prepared = prepared_result.value
        run_result = run(
            config=prepared.config,
            file_system=OverlayFileSystem(base, overlay),
            predicate_registry=prepared.predicate_registry,
            report_suppression_warnings=prepared.diagnostic_level_value != "error",
            target_files=frozenset(overlay.keys()),
            baseline=baseline_result.value,
            # unusedCode findings are warnings by default, so they can only
            # ever change the block/pass outcome when `--error-on-warnings`
            # is set. It's also by far the most expensive lane (a
            # whole-project scan on every single-file gate call), so skip it
            # unless the caller opted into warnings blocking too.
            run_unused_code=error_on_warnings,
        )

        if ruff and ruff_py_paths:
            ruff_result = run_ruff_on_overlay(overlay, cwd=Path.cwd())
            if isinstance(ruff_result, Err):
                status = "verification-unavailable" if fail_closed else "skip"
                return _GateOutcome(status=status, detail=ruff_result.error)
            if ruff_result.value:
                run_result = replace(
                    run_result,
                    diagnostics=[*run_result.diagnostics, *ruff_result.value],
                )
    except Exception as error:  # pragma: no cover - exercised by monkeypatch tests.
        detail = str(error) or error.__class__.__name__
        status = "verification-unavailable" if fail_closed else "skip"
        return _GateOutcome(status=status, detail=detail)

    should_block = has_errors(run_result) or (
        error_on_warnings and has_warnings(run_result)
    )
    if should_block:
        return _GateOutcome(status="violation", run_result=run_result)
    return _GateOutcome(status="pass")


def _exit_code_for_outcome(outcome: _GateOutcome, *, max_diagnostics: int) -> int:
    """Map a computed outcome to the gate's exit code, writing stderr as needed."""
    if outcome.status == "violation":
        assert outcome.run_result is not None
        sys.stderr.write(
            _format_blocking_json(run_result=outcome.run_result, max_diagnostics=max_diagnostics)
        )
        sys.stderr.write("\n")
        return 2

    if outcome.status == "verification-unavailable":
        sys.stderr.write(
            f"konpy gate: verification unavailable: {outcome.detail} (blocking: --fail-closed)\n"
        )
        return 2

    if outcome.status == "skip" and outcome.detail is not None:
        _write_warning(outcome.detail)

    return 0


def _format_blocking_json(*, run_result: RunResult, max_diagnostics: int) -> str:
    truncation = truncate_diagnostics(
        diagnostics=run_result.diagnostics,
        max=max_diagnostics,
    )
    reported_result = RunResult(
        diagnostics=truncation.diagnostics,
        files_checked=run_result.files_checked,
        duration_ms=run_result.duration_ms,
        suppressed_diagnostics=run_result.suppressed_diagnostics,
        baselined_diagnostics=run_result.baselined_diagnostics,
        baseline_stale_entries=run_result.baseline_stale_entries,
    )
    total_errors, total_warnings = count_severities(run_result.diagnostics)
    return format_json(
        reported_result,
        show_suppressed=False,
        total_errors=total_errors,
        total_warnings=total_warnings,
        omitted=truncation.omitted,
    )


def _write_warning(detail: str) -> None:
    sys.stderr.write(f"konpy gate: warning: {detail}\n")
