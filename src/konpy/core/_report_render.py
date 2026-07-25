"""Plain-text rendering for the zero-config codebase report.

Section style follows fallow's bare-run report: a metrics header, one
`──`-ruled section per lane, capped listings with an "... and N more" tail,
and a pointer line per section into `konpy docs`.
"""

from __future__ import annotations

from konpy.core.report import ReportData
from konpy.predicates.restrict_duplicate_functions import DEFAULT_MIN_STATEMENTS
from konpy.predicates.restrict_repeated_literals import (
    DEFAULT_MAX_OCCURRENCES,
    DEFAULT_MIN_LENGTH,
)
from konpy.unused.engine import DEFAULT_TEST_GLOBS

_TOP = 10


def _percent(pair: tuple[int, int]) -> str:
    have, total = pair
    if total == 0:
        return "n/a"
    return f"{have}/{total} ({round(100 * have / total)}%)"


def _rule(title: str) -> str:
    return f"── {title} {'─' * max(4, 46 - len(title))}"


def _header(data: ReportData) -> list[str]:
    conventions = data.conventions
    if conventions.status == "clean":
        conventions_note = "conventions clean"
    elif conventions.status == "violations":
        conventions_note = (
            f"conventions {conventions.errors} errors, {conventions.warnings} warnings"
        )
    elif conventions.status == "invalid":
        conventions_note = "konpy.json invalid"
    else:
        conventions_note = "no konpy.json"

    files_note = f"{data.files} files"
    if data.generated_files:
        files_note += f" ({data.generated_files} generated)"

    return [
        f"■ konpy report · {files_note} · {data.loc:,} LOC · {conventions_note} · "
        f"{len(data.unused)} unused defs · {len(data.literal_groups)} repeated literals · "
        f"{len(data.function_groups)} duplicate-function groups",
    ]


def _conventions_section(data: ReportData) -> list[str]:
    conventions = data.conventions
    lines = [_rule("Conventions")]
    if conventions.status == "missing":
        lines.append(
            "  no konpy.json found — run `konpy init` to adopt the strict starter config"
        )
        return lines
    if conventions.status == "invalid":
        lines.append("  konpy.json is invalid:")
        lines.extend(f"  {line}" for line in (conventions.error_text or "").splitlines()[:4])
        return lines
    if conventions.status == "clean":
        lines.append(f"✓ {conventions.files_checked} files checked · no violations")
        return lines

    lines.append(
        f"✗ {conventions.errors} errors · {conventions.warnings} warnings "
        f"across {conventions.files_checked} files"
    )
    for diagnostic in conventions.top_diagnostics[:_TOP]:
        location = f"{diagnostic.file_path}:{diagnostic.line}" if diagnostic.line else (
            diagnostic.file_path
        )
        lines.append(
            f"  {diagnostic.severity:<7} {location}  {diagnostic.message}"
            f"  [{diagnostic.convention_name or diagnostic.predicate_name}]"
        )
    remaining = len(conventions.top_diagnostics) - _TOP
    if remaining > 0:
        lines.append(f"  ... and {remaining} more — run `konpy check` for the full list")
    return lines


def _unused_section(data: ReportData) -> list[str]:
    lines = [_rule("Unused code")]
    if not data.unused:
        lines.append("✓ no unused definitions found")
    else:
        lines.append(f"● Unused definitions ({len(data.unused)})")
        for diagnostic in data.unused[:_TOP]:
            lines.append(f"  {diagnostic.file_path}:{diagnostic.line}  {diagnostic.message}")
        remaining = len(data.unused) - _TOP
        if remaining > 0:
            lines.append(f"  ... and {remaining} more")
    if data.generated_files:
        lines.append(
            f"  {data.generated_files} generated files (auto-generated banner)"
            " feed references only"
        )
    lines.append(
        f"  test files feed references only ({', '.join(DEFAULT_TEST_GLOBS)})"
        " — konpy docs unused-code"
    )
    return lines


def _duplication_section(data: ReportData) -> list[str]:
    lines = [_rule("Duplication")]
    if not data.literal_groups and not data.function_groups:
        lines.append("✓ no repeated literals or duplicate functions at default thresholds")
    if data.literal_groups:
        worst = max(group.occurrences for group in data.literal_groups)
        lines.append(
            f"● Repeated string literals ({len(data.literal_groups)} values · worst x{worst}"
            " · ranked by count x length, mapping-key values last)"
        )
        for group in data.literal_groups[:_TOP]:
            shown = group.value if len(group.value) <= 40 else f"{group.value[:37]}..."
            tag = f"  [{group.label}]" if group.label else ""
            lines.append(
                f'  x{group.occurrences}  "{shown}"  first at {group.first_path}:'
                f"{group.first_line}{tag}"
            )
        remaining = len(data.literal_groups) - _TOP
        if remaining > 0:
            lines.append(f"  ... and {remaining} more values")
    if data.function_groups:
        lines.append(
            f"● Duplicate function implementations ({len(data.function_groups)} groups)"
        )
        for group in data.function_groups[:_TOP]:
            sites = " ↔ ".join(f"{path}:{line}" for path, line in group.members)
            tag = f"  [{group.label}]" if group.label else ""
            variants = f" a.k.a. {', '.join(group.name_variants)}" if group.name_variants else ""
            lines.append(
                f"  x{len(group.members)}  {group.name}{variants}"
                f" ({group.statement_count} statements)  {sites}{tag}"
            )
        remaining = len(data.function_groups) - _TOP
        if remaining > 0:
            lines.append(f"  ... and {remaining} more groups")
    lines.append(
        f"  tests excluded; thresholds: literals ≥{DEFAULT_MIN_LENGTH} chars"
        f" x>{DEFAULT_MAX_OCCURRENCES}, functions ≥{DEFAULT_MIN_STATEMENTS} statements"
        " — konpy docs predicates"
    )
    return lines


def _coverage_section(data: ReportData) -> list[str]:
    coverage = data.coverage
    scope = "non-test, non-generated files" if data.generated_files else "non-test files"
    return [
        _rule(f"Coverage ({scope})"),
        f"  docstrings   modules {_percent(coverage.module_docs)} · "
        f"classes {_percent(coverage.class_docs)} · "
        f"public functions {_percent(coverage.function_docs)}",
        f"  annotations  fully annotated public functions {_percent(coverage.annotated_functions)}",
        "  `konpy infer` proposes enforceable ratchet rules from these signals",
    ]


def render_report(data: ReportData) -> str:
    """Render the assembled report as plain text."""
    skipped_note = (
        [f"  note: {data.skipped_unparsable} unreadable/unparsable files skipped"]
        if data.skipped_unparsable
        else []
    )
    footer = (
        f"Analyzed {data.files} files ({data.test_files} test) in "
        f"{data.duration_ms:.0f}ms. Next: konpy check · konpy infer · konpy docs"
    )
    sections = [
        *_header(data),
        *skipped_note,
        "",
        *_conventions_section(data),
        "",
        *_unused_section(data),
        "",
        *_duplication_section(data),
        "",
        *_coverage_section(data),
        "",
        footer,
    ]
    return "\n".join(sections)


__all__ = ["render_report"]
