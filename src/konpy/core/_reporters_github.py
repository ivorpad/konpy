from __future__ import annotations

from konpy.core._reporters_shared import _format_stale_baseline_message, _format_suppressed_by
from konpy.core.baseline import BaselineStaleEntry
from konpy.core.diagnostics import Diagnostic
from konpy.core.runner import RunResult
from konpy.core.suppressions import SuppressedDiagnostic


def _format_github_annotation(diagnostic: Diagnostic) -> str:
    annotation = f"::{diagnostic.severity} file={diagnostic.file_path}"
    if diagnostic.line is not None:
        annotation += f",line={diagnostic.line}"
    if diagnostic.convention_name:
        annotation += f",title={diagnostic.convention_name}"
    annotation += f"::{diagnostic.message}"
    return annotation


def _format_github_suppressed_notice(item: SuppressedDiagnostic) -> str:
    diagnostic = item.diagnostic
    title = (
        f"Suppressed {diagnostic.convention_name}"
        if diagnostic.convention_name
        else "Suppressed diagnostic"
    )

    annotation = f"::notice file={diagnostic.file_path}"
    if diagnostic.line is not None:
        annotation += f",line={diagnostic.line}"
    annotation += f",title={title}"
    annotation += (
        f"::{diagnostic.severity}: {diagnostic.message} "
        f"({_format_suppressed_by(item)})"
    )
    return annotation


def _format_github_baselined_notice(diagnostic: Diagnostic) -> str:
    title = (
        f"Baselined {diagnostic.convention_name}"
        if diagnostic.convention_name
        else "Baselined diagnostic"
    )

    annotation = f"::notice file={diagnostic.file_path}"
    if diagnostic.line is not None:
        annotation += f",line={diagnostic.line}"
    annotation += f",title={title}::{diagnostic.severity}: {diagnostic.message}"
    return annotation


def _format_github_stale_baseline_notice(entry: BaselineStaleEntry) -> str:
    return f"::warning title=Stale baseline entry::{_format_stale_baseline_message(entry)}"


def format_github(
    result: RunResult,
    *,
    show_suppressed: bool = False,
    show_baselined: bool = False,
) -> str:
    """Render a run result as GitHub Actions workflow-command annotations."""
    lines: list[str] = []

    for diagnostic in result.diagnostics:
        lines.append(_format_github_annotation(diagnostic))

    if show_baselined:
        for item in result.baselined_diagnostics:
            lines.append(_format_github_baselined_notice(item.diagnostic))

    if show_suppressed:
        for suppressed in result.suppressed_diagnostics:
            lines.append(_format_github_suppressed_notice(suppressed))

    for entry in result.baseline_stale_entries:
        lines.append(_format_github_stale_baseline_notice(entry))

    return "\n".join(lines)


__all__ = ["format_github"]
