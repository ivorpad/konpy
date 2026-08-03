from __future__ import annotations

import sys
from collections.abc import Callable

from konpy.core._reporters_shared import (
    _baselined_as_diagnostics,
    _display_file_path,
    _format_diagnostic_extra,
    _format_stale_baseline_message,
    _format_summary,
    _format_suppressed_by,
    _group_by_file,
    _group_suppressed_by_file,
    _max_line_width,
    _max_suppressed_line_width,
    _sort_diagnostics,
    count_severities,
)
from konpy.core.baseline import BaselinedDiagnostic, BaselineStaleEntry
from konpy.core.diagnostics import Diagnostic
from konpy.core.runner import RunResult
from konpy.core.suppressions import SuppressedDiagnostic

ColorFn = Callable[[str], str]


def _identity(value: str) -> str:
    return value


def _ansi(open_code: str, close_code: str) -> ColorFn:
    def color(value: str) -> str:
        return f"\x1b[{open_code}m{value}\x1b[{close_code}m"

    return color


def _palette(use_colors: bool) -> dict[str, ColorFn]:
    if not use_colors:
        return {
            "red": _identity,
            "yellow": _identity,
            "green": _identity,
            "bold": _identity,
            "dim": _identity,
        }

    return {
        "red": _ansi("31", "39"),
        "yellow": _ansi("33", "39"),
        "green": _ansi("32", "39"),
        "bold": _ansi("1", "22"),
        "dim": _ansi("2", "22"),
    }


def _format_diagnostic_line(
    *,
    diagnostic: Diagnostic,
    line_width: int,
    red: ColorFn,
    yellow: ColorFn,
    dim: ColorFn,
) -> str:
    line = "-" if diagnostic.line is None else str(diagnostic.line)
    padded_line = line.rjust(line_width)
    color = yellow if diagnostic.severity == "warning" else red
    severity = color(diagnostic.severity)
    convention = ""

    if diagnostic.convention_name is not None:
        convention = f"  {dim(f'[{diagnostic.convention_name}]')}"

    return f"  {padded_line}  {severity}  {diagnostic.message}{convention}"


def _format_file_group(
    *,
    file_path: str,
    diagnostics: list[Diagnostic],
    bold: ColorFn,
    red: ColorFn,
    yellow: ColorFn,
    dim: ColorFn,
) -> list[str]:
    sorted_diagnostics = _sort_diagnostics(diagnostics)
    line_width = _max_line_width(sorted_diagnostics)
    lines = [bold(_display_file_path(file_path))]

    for diagnostic in sorted_diagnostics:
        lines.append(
            _format_diagnostic_line(
                diagnostic=diagnostic,
                line_width=line_width,
                red=red,
                yellow=yellow,
                dim=dim,
            )
        )
        extra = _format_diagnostic_extra(diagnostic)
        if extra is not None:
            lines.append(f"        {dim('-> ' + extra)}")

    lines.append("")
    return lines


def _format_suppressed_default_section(
    *,
    suppressed: list[SuppressedDiagnostic],
    bold: ColorFn,
    dim: ColorFn,
) -> list[str]:
    lines = ["Suppressed diagnostics:"]

    for file_path, file_suppressed in _group_suppressed_by_file(suppressed).items():
        line_width = _max_suppressed_line_width(file_suppressed)
        lines.append(bold(_display_file_path(file_path)))

        for item in file_suppressed:
            diagnostic = item.diagnostic
            line = "-" if diagnostic.line is None else str(diagnostic.line)
            padded_line = line.rjust(line_width)
            convention = (
                f"  {dim(f'[{diagnostic.convention_name}]')}"
                if diagnostic.convention_name is not None
                else ""
            )
            lines.append(
                "  "
                f"{padded_line}  "
                f"suppressed {diagnostic.severity}  "
                f"{diagnostic.message}"
                f"{convention}  "
                f"({_format_suppressed_by(item)})"
            )

        lines.append("")

    return lines


def _format_baselined_default_section(
    *,
    baselined: list[BaselinedDiagnostic],
    bold: ColorFn,
    red: ColorFn,
    yellow: ColorFn,
    dim: ColorFn,
) -> list[str]:
    lines = ["Baselined diagnostics:"]

    grouped = _group_by_file(_baselined_as_diagnostics(baselined))
    for file_path, file_diagnostics in grouped.items():
        lines.extend(
            _format_file_group(
                file_path=file_path,
                diagnostics=file_diagnostics,
                bold=bold,
                red=red,
                yellow=yellow,
                dim=dim,
            )
        )

    return lines


def _format_stale_baseline_default_section(
    *,
    stale_entries: list[BaselineStaleEntry],
    yellow: ColorFn,
) -> list[str]:
    lines = ["Stale baseline entries:"]
    for entry in stale_entries:
        lines.append(f"  {yellow(_format_stale_baseline_message(entry))}")
    lines.append("")
    return lines


def format_default(
    result: RunResult,
    *,
    colors: bool | None = None,
    show_suppressed: bool = False,
    show_baselined: bool = False,
) -> str:
    """Render a run result as the human-readable terminal report."""
    use_colors = sys.stdout.isatty() if colors is None else colors
    palette = _palette(use_colors)

    diagnostics = result.diagnostics
    lines: list[str] = []

    if diagnostics:
        for file_path, file_diagnostics in _group_by_file(diagnostics).items():
            lines.extend(
                _format_file_group(
                    file_path=file_path,
                    diagnostics=file_diagnostics,
                    bold=palette["bold"],
                    red=palette["red"],
                    yellow=palette["yellow"],
                    dim=palette["dim"],
                )
            )

    if show_baselined and result.baselined_diagnostics:
        lines.extend(
            _format_baselined_default_section(
                baselined=result.baselined_diagnostics,
                bold=palette["bold"],
                red=palette["red"],
                yellow=palette["yellow"],
                dim=palette["dim"],
            )
        )

    if show_suppressed and result.suppressed_diagnostics:
        lines.extend(
            _format_suppressed_default_section(
                suppressed=result.suppressed_diagnostics,
                bold=palette["bold"],
                dim=palette["dim"],
            )
        )

    if result.baseline_stale_entries:
        lines.extend(
            _format_stale_baseline_default_section(
                stale_entries=result.baseline_stale_entries,
                yellow=palette["yellow"],
            )
        )

    error_count, warning_count = count_severities(diagnostics)
    lines.append(
        _format_summary(
            files_checked=result.files_checked,
            error_count=error_count,
            warning_count=warning_count,
            suppressed_count=len(result.suppressed_diagnostics),
            duration_ms=result.duration_ms,
            baselined_count=len(result.baselined_diagnostics),
        )
    )

    return "\n".join(lines)


__all__ = ["format_default"]
