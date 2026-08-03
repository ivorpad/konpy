from __future__ import annotations

import json

from konpy.core._reporters_shared import count_severities
from konpy.core.baseline import BaselineStaleEntry
from konpy.core.diagnostics import Diagnostic
from konpy.core.runner import RunResult
from konpy.core.suppressions import SuppressedDiagnostic


def _diagnostic_to_json(diagnostic: Diagnostic) -> dict[str, object]:
    item: dict[str, object] = {
        "severity": diagnostic.severity,
        "conventionName": diagnostic.convention_name,
        "filePath": diagnostic.file_path,
        "predicateName": diagnostic.predicate_name,
        "message": diagnostic.message,
    }
    if diagnostic.line is not None:
        item["line"] = diagnostic.line
    if diagnostic.description is not None:
        item["description"] = diagnostic.description
    if diagnostic.hint is not None:
        item["hint"] = diagnostic.hint
    if diagnostic.expected is not None:
        item["expected"] = diagnostic.expected
    if diagnostic.found is not None:
        item["found"] = diagnostic.found
    if diagnostic.fix_hint is not None:
        item["fixHint"] = diagnostic.fix_hint
    return item


def _suppressed_diagnostic_to_json(
    suppressed: SuppressedDiagnostic,
) -> dict[str, object]:
    item = _diagnostic_to_json(suppressed.diagnostic)
    suppressed_by: dict[str, object] = {
        "kind": suppressed.suppression.kind,
        "filePath": suppressed.suppression.file_path,
        "line": suppressed.suppression.line,
    }
    if suppressed.suppression.reason is not None:
        suppressed_by["reason"] = suppressed.suppression.reason
    item["suppressedBy"] = suppressed_by
    return item


def _baseline_stale_entry_to_json(entry: BaselineStaleEntry) -> dict[str, object]:
    return {
        "filePath": entry.file_path,
        "conventionName": entry.convention_name,
        "recorded": entry.recorded_count,
        "found": entry.found_count,
    }


def format_json(
    result: RunResult,
    *,
    show_suppressed: bool = False,
    show_baselined: bool = False,
    total_errors: int | None = None,
    total_warnings: int | None = None,
    omitted: int = 0,
) -> str:
    """Render a run result as a single parseable JSON object.

    ``result.diagnostics`` is the (possibly truncated) set to list under the
    ``diagnostics`` key. ``total_errors``/``total_warnings``, when given,
    populate ``summary.errors``/``summary.warnings`` from the full
    pre-truncation diagnostic set instead of counting ``result.diagnostics``
    -- so a truncated view never under-reports the real totals. The
    ``truncation`` key is always present, reporting how many diagnostics were
    shown (``len(result.diagnostics)``) versus omitted by the cap.

    ``baselined`` (diagnostics demoted by a baseline, same element shape as
    ``diagnostics``) and ``baselineStale`` (stale baseline entries) are
    always present in full, regardless of ``show_suppressed``/
    ``show_baselined`` -- those flags only affect human-readable formats, the
    same way ``show_suppressed`` never changes ``suppressed`` here.
    """
    del show_suppressed
    del show_baselined

    error_count, warning_count = count_severities(result.diagnostics)

    output: dict[str, object] = {
        "diagnostics": [_diagnostic_to_json(diagnostic) for diagnostic in result.diagnostics],
        "suppressed": [
            _suppressed_diagnostic_to_json(suppressed)
            for suppressed in result.suppressed_diagnostics
        ],
        "baselined": [
            _diagnostic_to_json(item.diagnostic) for item in result.baselined_diagnostics
        ],
        "baselineStale": [
            _baseline_stale_entry_to_json(entry) for entry in result.baseline_stale_entries
        ],
        "summary": {
            "filesChecked": result.files_checked,
            "errors": error_count if total_errors is None else total_errors,
            "warnings": warning_count if total_warnings is None else total_warnings,
            "suppressed": len(result.suppressed_diagnostics),
            "baselined": len(result.baselined_diagnostics),
            "durationMs": result.duration_ms,
        },
        "truncation": {
            "shown": len(result.diagnostics),
            "omitted": omitted,
        },
    }

    return json.dumps(output, indent=2)


__all__ = ["format_json"]
