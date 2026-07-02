from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Literal

from konsistent.core.diagnostics import Diagnostic
from konsistent.core.format_time import format_time
from konsistent.core.runner import RunResult
from konsistent.core.suppressions import SuppressedDiagnostic

ReporterFormat = Literal["default", "json", "github", "markdown"]
ColorFn = Callable[[str], str]


def resolve_format(
    *,
    format: str,
    env: Mapping[str, str] | None = None,
) -> str:
    if format != "default":
        return format

    environment = os.environ if env is None else env
    if environment.get("GITHUB_ACTIONS") == "true":
        return "github"

    return "default"


def format_default(
    result: RunResult,
    *,
    colors: bool | None = None,
    show_suppressed: bool = False,
) -> str:
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

    if show_suppressed and result.suppressed_diagnostics:
        lines.extend(
            _format_suppressed_default_section(
                suppressed=result.suppressed_diagnostics,
                bold=palette["bold"],
                dim=palette["dim"],
            )
        )

    error_count, warning_count = _count_severities(diagnostics)
    lines.append(
        _format_summary(
            files_checked=result.files_checked,
            error_count=error_count,
            warning_count=warning_count,
            suppressed_count=len(result.suppressed_diagnostics),
            duration_ms=result.duration_ms,
        )
    )

    return "\n".join(lines)


def format_json(
    result: RunResult,
    *,
    show_suppressed: bool = False,
) -> str:
    del show_suppressed

    output: dict[str, object] = {
        "diagnostics": [_diagnostic_to_json(diagnostic) for diagnostic in result.diagnostics],
        "suppressed": [
            _suppressed_diagnostic_to_json(suppressed)
            for suppressed in result.suppressed_diagnostics
        ],
        "summary": {
            "filesChecked": result.files_checked,
            "errors": _count_severities(result.diagnostics)[0],
            "warnings": _count_severities(result.diagnostics)[1],
            "suppressed": len(result.suppressed_diagnostics),
            "durationMs": result.duration_ms,
        },
    }

    return json.dumps(output, indent=2)


def format_github(
    result: RunResult,
    *,
    show_suppressed: bool = False,
) -> str:
    lines: list[str] = []

    for diagnostic in result.diagnostics:
        lines.append(_format_github_annotation(diagnostic))

    if show_suppressed:
        for suppressed in result.suppressed_diagnostics:
            lines.append(_format_github_suppressed_notice(suppressed))

    return "\n".join(lines)


def format_markdown(
    result: RunResult,
    *,
    show_suppressed: bool = False,
) -> str:
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
                rows.append(
                    "| "
                    f"{line} | "
                    f"{diagnostic.severity} | "
                    f"{diagnostic.message} | "
                    f"{convention} |"
                )
            sections.append("\n".join(rows))

    if show_suppressed and result.suppressed_diagnostics:
        sections.append(
            _format_suppressed_markdown_section(result.suppressed_diagnostics)
        )

    error_count, warning_count = _count_severities(diagnostics)
    sections.append(
        "**"
        + _format_summary(
            files_checked=result.files_checked,
            error_count=error_count,
            warning_count=warning_count,
            suppressed_count=len(result.suppressed_diagnostics),
            duration_ms=result.duration_ms,
        )
        + "**"
    )

    return "\n\n".join(sections)


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

    lines.append("")
    return lines


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


def _format_suppressed_by(item: SuppressedDiagnostic) -> str:
    text = f"suppressed by line {item.suppression.line}"
    if item.suppression.reason:
        text += f": {item.suppression.reason}"
    return text


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


def _count_severities(diagnostics: list[Diagnostic]) -> tuple[int, int]:
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


__all__ = [
    "ReporterFormat",
    "format_default",
    "format_github",
    "format_json",
    "format_markdown",
    "resolve_format",
]
