"""PreToolUse deterministic gate for proposed Claude Code writes."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from konpy.cli._check_support import (
    has_errors,
    has_warnings,
    prepare_check_runtime,
)
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
) -> int:
    """Run the `konpy gate` PreToolUse flow.

    Exit 2 is reserved exclusively for verified convention violations in the
    proposed content. Payload skips, unreconstructable content, config errors,
    and runtime failures all fail open with exit 0.
    """
    del env

    raw_stdin = stdin_text if stdin_text is not None else sys.stdin.read()
    payload = parse_hook_payload(raw_stdin)
    if payload is None:
        return 0

    if payload.tool_name not in CLAUDE_WRITE_TOOLS:
        return 0

    target_paths = extract_target_paths(payload)
    if not target_paths:
        return 0

    matched_paths = [
        path for path in target_paths if not match or path_matches_any(path, match)
    ]
    if not matched_paths:
        return 0

    try:
        base = file_system if file_system is not None else RealFileSystem(cwd=Path.cwd())

        reconstructed = reconstruct_proposed_content(payload, base=base)
        if reconstructed is None:
            return 0

        overlay = {
            path: content for path, content in reconstructed.items() if path in matched_paths
        }
        if not overlay:
            return 0

        prepared_result = prepare_check_runtime(
            config_path=config_path,
            config_package=config_package,
            diagnostic_level=diagnostic_level,
            placeholder=placeholder,
        )
        if isinstance(prepared_result, Err):
            _write_warning(prepared_result.error)
            return 0

        prepared = prepared_result.value
        run_result = run(
            config=prepared.config,
            file_system=OverlayFileSystem(base, overlay),
            predicate_registry=prepared.predicate_registry,
            report_suppression_warnings=prepared.diagnostic_level_value != "error",
            target_files=frozenset(overlay.keys()),
        )
    except Exception as error:  # pragma: no cover - exercised by monkeypatch tests.
        _write_warning(str(error) or error.__class__.__name__)
        return 0

    should_block = has_errors(run_result) or (
        error_on_warnings and has_warnings(run_result)
    )
    if not should_block:
        return 0

    sys.stderr.write(
        _format_blocking_json(run_result=run_result, max_diagnostics=max_diagnostics)
    )
    sys.stderr.write("\n")
    return 2


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
