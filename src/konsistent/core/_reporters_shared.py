from __future__ import annotations

from konsistent.core.diagnostics import Diagnostic
from konsistent.core.format_time import format_time
from konsistent.core.suppressions import SuppressedDiagnostic


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(
        diagnostics,
        key=lambda diagnostic: diagnostic.line if diagnostic.line is not None else -1,
    )


def _sort_suppressed(
    suppressed: list[SuppressedDiagnostic],
) -> list[SuppressedDiagnostic]:
    return sorted(
        suppressed,
        key=lambda item: (
            item.diagnostic.file_path,
            item.diagnostic.line if item.diagnostic.line is not None else -1,
            item.diagnostic.column if item.diagnostic.column is not None else -1,
            item.diagnostic.message,
        ),
    )


def _group_by_file(diagnostics: list[Diagnostic]) -> dict[str, list[Diagnostic]]:
    grouped: dict[str, list[Diagnostic]] = {}

    for diagnostic in diagnostics:
        grouped.setdefault(diagnostic.file_path, []).append(diagnostic)

    return grouped


def _group_suppressed_by_file(
    suppressed: list[SuppressedDiagnostic],
) -> dict[str, list[SuppressedDiagnostic]]:
    grouped: dict[str, list[SuppressedDiagnostic]] = {}

    for item in _sort_suppressed(suppressed):
        grouped.setdefault(item.diagnostic.file_path, []).append(item)

    return grouped


def _max_line_width(diagnostics: list[Diagnostic]) -> int:
    width = 1

    for diagnostic in diagnostics:
        current = 1 if diagnostic.line is None else len(str(diagnostic.line))
        width = max(width, current)

    return width


def _max_suppressed_line_width(
    suppressed: list[SuppressedDiagnostic],
) -> int:
    width = 1

    for item in suppressed:
        current = 1 if item.diagnostic.line is None else len(str(item.diagnostic.line))
        width = max(width, current)

    return width


def _display_file_path(file_path: str) -> str:
    if file_path == ".":
        return "(project root)"
    return file_path


def _format_diagnostic_extra(diagnostic: Diagnostic) -> str | None:
    """Build the additive intent/direction suffix for default and markdown output.

    Returns ``None`` when the diagnostic carries none of description/hint/
    expected/found/fix_hint -- the gate that keeps every diagnostic untouched
    by this feature byte-identical to prior output.
    """
    parts: list[str] = []
    if diagnostic.description is not None:
        parts.append(f"description: {diagnostic.description}")
    if diagnostic.hint is not None:
        parts.append(f"hint: {diagnostic.hint}")
    if diagnostic.expected is not None:
        parts.append(f"expected: {diagnostic.expected}")
    if diagnostic.found is not None:
        parts.append(f"found: {diagnostic.found}")
    if diagnostic.fix_hint is not None:
        parts.append(f"fix: {diagnostic.fix_hint}")
    if not parts:
        return None
    return " | ".join(parts)


def _format_suppressed_by(item: SuppressedDiagnostic) -> str:
    text = f"suppressed by line {item.suppression.line}"
    if item.suppression.reason:
        text += f": {item.suppression.reason}"
    return text


def count_severities(diagnostics: list[Diagnostic]) -> tuple[int, int]:
    """Count error- and warning-severity diagnostics.

    Returns an ``(error_count, warning_count)`` tuple.
    """
    error_count = sum(1 for diagnostic in diagnostics if diagnostic.severity == "error")
    warning_count = sum(1 for diagnostic in diagnostics if diagnostic.severity == "warning")
    return error_count, warning_count


def _format_summary(
    *,
    files_checked: int,
    error_count: int,
    warning_count: int,
    suppressed_count: int,
    duration_ms: float | None,
) -> str:
    file_word = "file" if files_checked == 1 else "files"
    checked = f"Checked {files_checked} {file_word} in {format_time(duration_ms or 0)}."

    if error_count == 0 and warning_count == 0:
        if suppressed_count == 0:
            return f"{checked} No violations found."
        suppressed_note = _format_suppressed_count(suppressed_count)
        return f"{checked} No unsuppressed violations found. {suppressed_note}."

    parts: list[str] = []
    if error_count > 0:
        error_word = "error" if error_count == 1 else "errors"
        parts.append(f"{error_count} {error_word}")
    if warning_count > 0:
        warning_word = "warning" if warning_count == 1 else "warnings"
        parts.append(f"{warning_count} {warning_word}")

    summary = f"{checked} Found {' and '.join(parts)}."
    if suppressed_count > 0:
        summary += f" {_format_suppressed_count(suppressed_count)}."
    return summary


def _format_suppressed_count(count: int) -> str:
    finding_word = "finding" if count == 1 else "findings"
    return f"Suppressed {count} {finding_word}"


__all__ = ["count_severities"]
