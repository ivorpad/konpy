from __future__ import annotations

from konpy.core._reporters_shared import (
    _baselined_as_diagnostics,
    _display_file_path,
    _format_diagnostic_extra,
    _format_stale_baseline_message,
    _format_summary,
    _group_by_file,
    _group_suppressed_by_file,
    _sort_diagnostics,
    count_severities,
)
from konpy.core.baseline import BaselinedDiagnostic, BaselineStaleEntry
from konpy.core.runner import RunResult
from konpy.core.suppressions import SuppressedDiagnostic


def _format_suppressed_markdown_section(
    suppressed: list[SuppressedDiagnostic],
) -> str:
    sections = ["### Suppressed diagnostics"]

    for file_path, file_suppressed in _group_suppressed_by_file(suppressed).items():
        rows = [
            f"**`{_display_file_path(file_path)}`**",
            "",
            "| Line | Severity | Message | Convention | Suppressed By | Reason |",
            "|------|----------|---------|------------|---------------|--------|",
        ]

        for item in file_suppressed:
            diagnostic = item.diagnostic
            line = "-" if diagnostic.line is None else str(diagnostic.line)
            convention = diagnostic.convention_name or ""
            reason = item.suppression.reason or ""
            rows.append(
                "| "
                f"{line} | "
                f"{diagnostic.severity} | "
                f"{diagnostic.message} | "
                f"{convention} | "
                f"line {item.suppression.line} | "
                f"{reason} |"
            )

        sections.append("\n".join(rows))

    return "\n\n".join(sections)


def _format_baselined_markdown_section(baselined: list[BaselinedDiagnostic]) -> str:
    sections = ["### Baselined diagnostics"]

    grouped = _group_by_file(_baselined_as_diagnostics(baselined))
    for file_path, file_diagnostics in grouped.items():
        rows = [
            f"**`{_display_file_path(file_path)}`**",
            "",
            "| Line | Severity | Message | Convention |",
            "|------|----------|---------|------------|",
        ]
        for diagnostic in _sort_diagnostics(file_diagnostics):
            line = "-" if diagnostic.line is None else str(diagnostic.line)
            convention = diagnostic.convention_name or ""
            rows.append(
                f"| {line} | {diagnostic.severity} | {diagnostic.message} | {convention} |"
            )
        sections.append("\n".join(rows))

    return "\n\n".join(sections)


def _format_stale_baseline_markdown_section(stale_entries: list[BaselineStaleEntry]) -> str:
    rows = ["### Stale baseline entries", ""]
    for entry in stale_entries:
        rows.append(f"- {_format_stale_baseline_message(entry)}")
    return "\n".join(rows)


def format_markdown(
    result: RunResult,
    *,
    show_suppressed: bool = False,
    show_baselined: bool = False,
) -> str:
    """Render a run result as a Markdown report suitable for PR comments."""
    diagnostics = result.diagnostics
    sections: list[str] = []

    if diagnostics:
        for file_path, file_diagnostics in _group_by_file(diagnostics).items():
            rows = [
                f"**`{_display_file_path(file_path)}`**",
                "",
                "| Line | Severity | Message | Convention |",
                "|------|----------|---------|------------|",
            ]
            for diagnostic in _sort_diagnostics(file_diagnostics):
                line = "-" if diagnostic.line is None else str(diagnostic.line)
                convention = diagnostic.convention_name or ""
                message_cell = diagnostic.message
                extra = _format_diagnostic_extra(diagnostic)
                if extra is not None:
                    message_cell = f"{message_cell}<br><sub>{extra}</sub>"
                rows.append(
                    "| "
                    f"{line} | "
                    f"{diagnostic.severity} | "
                    f"{message_cell} | "
                    f"{convention} |"
                )
            sections.append("\n".join(rows))

    if show_baselined and result.baselined_diagnostics:
        sections.append(_format_baselined_markdown_section(result.baselined_diagnostics))

    if show_suppressed and result.suppressed_diagnostics:
        sections.append(
            _format_suppressed_markdown_section(result.suppressed_diagnostics)
        )

    if result.baseline_stale_entries:
        sections.append(_format_stale_baseline_markdown_section(result.baseline_stale_entries))

    error_count, warning_count = count_severities(diagnostics)
    sections.append(
        "**"
        + _format_summary(
            files_checked=result.files_checked,
            error_count=error_count,
            warning_count=warning_count,
            suppressed_count=len(result.suppressed_diagnostics),
            duration_ms=result.duration_ms,
            baselined_count=len(result.baselined_diagnostics),
        )
        + "**"
    )

    return "\n\n".join(sections)


__all__ = ["format_markdown"]
