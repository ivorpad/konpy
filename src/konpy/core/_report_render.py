"""Plain-text rendering for the zero-config codebase report.

Section style follows fallow's bare-run report: a metrics header, one
`──`-ruled section per lane, capped listings with an "... and N more" tail,
and a next-step pointer per section (`konpy docs`, `konpy init`, or `konpy
infer`, whichever fits the lane). Conventions render first
(it's config policy, not an analysis finding); the analysis lanes after it
follow blast radius order: cross-component duplication compounds fastest,
dead code second, style debt (coverage) last.
"""

from __future__ import annotations

from konpy.core._report_conventions import DEFAULT_CONVENTIONS_SUMMARY
from konpy.core._report_tools import STATUS_LABEL
from konpy.core.diagnostics import Diagnostic
from konpy.core.report import ReportConventions, ReportData
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


def _count_noun(count: int, noun: str) -> str:
    suffix = "" if count == 1 else "s"
    return f"{count:,} {noun}{suffix}"


def _display_literal(value: str) -> str:
    # Escape control characters before truncating: a multi-line literal must
    # never splice raw newlines into the one-line-per-finding format.
    escaped = (
        value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    if len(escaped) <= 40:
        return escaped
    return f"{escaped[:37]}..."


def _header(data: ReportData) -> list[str]:
    conventions = data.conventions
    if conventions.status == "clean":
        conventions_note = "conventions clean"
    elif conventions.status == "violations":
        conventions_note = (
            f"conventions {_count_noun(conventions.errors, 'error')}, "
            f"{_count_noun(conventions.warnings, 'warning')}"
        )
    elif conventions.status == "invalid":
        conventions_note = "konpy.json invalid"
    elif conventions.status == "defaults":
        findings = conventions.errors + conventions.warnings
        conventions_note = (
            "defaults clean" if findings == 0 else f"defaults {_count_noun(findings, 'finding')}"
        )
    else:
        conventions_note = "no konpy.json"

    files_note = _count_noun(data.files, "file")
    if data.generated_files:
        files_note += f" ({data.generated_files} generated)"
    if data.vendor_files:
        files_note += f" ({data.vendor_files} vendored/template/ignored)"

    return [
        f"■ konpy report · {files_note} · {data.loc:,} LOC · {conventions_note} · "
        f"{_count_noun(len(data.unused), 'unused def')} · "
        f"{_count_noun(len(data.literal_groups), 'repeated literal')} · "
        f"{_count_noun(len(data.function_groups), 'duplicate-function group')}",
    ]


def _vendor_note(data: ReportData) -> list[str]:
    if not data.vendor_roots:
        return []
    shown = ", ".join(data.vendor_roots[:3])
    if len(data.vendor_roots) > 3:
        shown += " ..."
    return [f"  note: skipped vendor/template trees: {shown}"]


def _diagnostic_lines(diagnostics: tuple[Diagnostic, ...], overflow_hint: str) -> list[str]:
    lines: list[str] = []
    for diagnostic in diagnostics[:_TOP]:
        location = f"{diagnostic.file_path}:{diagnostic.line}" if diagnostic.line else (
            diagnostic.file_path
        )
        lines.append(
            f"  {diagnostic.severity:<7} {location}  {diagnostic.message}"
            f"  [{diagnostic.convention_name or diagnostic.predicate_name}]"
        )
    remaining = len(diagnostics) - _TOP
    if remaining > 0:
        lines.append(f"  ... and {remaining} more{overflow_hint}")
    return lines


def _defaults_section_lines(conventions: ReportConventions) -> list[str]:
    lines = [f"  no konpy.json — built-in defaults: {DEFAULT_CONVENTIONS_SUMMARY}"]
    findings = conventions.errors + conventions.warnings
    if findings == 0:
        lines.append("✓ defaults clean · `konpy init` adopts the full strict starter")
        return lines
    lines.append(f"● {_count_noun(findings, 'finding')} (advisory — exit code unaffected)")
    lines.extend(_diagnostic_lines(conventions.top_diagnostics, ""))
    lines.append("  `konpy init` writes the enforceable strict starter — `konpy check` gates it")
    return lines


def _conventions_section(data: ReportData) -> list[str]:
    conventions = data.conventions
    lines = [_rule("Conventions")]
    if conventions.status == "defaults":
        lines.extend(_defaults_section_lines(conventions))
        return lines
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
    lines.extend(
        _diagnostic_lines(
            conventions.top_diagnostics, " — run `konpy check` for the full list"
        )
    )
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
    if data.vendor_files:
        lines.append(
            f"  {data.vendor_files} vendored/template/ignored files feed references only"
            " — konpy report --include-vendored"
        )
    lines.append(
        f"  test files feed references only ({', '.join(DEFAULT_TEST_GLOBS)})"
        " — konpy docs unused-code"
    )
    return lines


def _duplication_section(data: ReportData) -> list[str]:
    # Function groups first: a duplicate spanning components is the fastest
    # blast radius in this report. Literal groups (mapping-key values last
    # among themselves) follow.
    lines = [_rule("Duplication")]
    if not data.literal_groups and not data.function_groups:
        lines.append("✓ no repeated literals or duplicate functions at default thresholds")
    if data.function_groups:
        lines.append(
            "● Duplicate function implementations "
            f"({_count_noun(len(data.function_groups), 'group')})"
        )
        for group in data.function_groups[:_TOP]:
            sites = " ↔ ".join(f"{path}:{line}" for path, line in group.members)
            cross_tag = "  [cross-component]" if group.is_cross_component else ""
            label_tag = f"  [{group.label}]" if group.label else ""
            variants = f" a.k.a. {', '.join(group.name_variants)}" if group.name_variants else ""
            lines.append(
                f"  x{len(group.members)}  {group.name}{variants}"
                f" ({group.statement_count} statements)  {sites}{cross_tag}{label_tag}"
            )
        remaining = len(data.function_groups) - _TOP
        if remaining > 0:
            lines.append(f"  ... and {remaining} more groups")
    if data.literal_groups:
        worst = max(group.occurrences for group in data.literal_groups)
        lines.append(
            f"● Repeated string literals ({_count_noun(len(data.literal_groups), 'value')}"
            f" · worst x{worst} · ranked by count x length, mapping-key values last)"
        )
        for group in data.literal_groups[:_TOP]:
            shown = _display_literal(group.value)
            tag = f"  [{group.label}]" if group.label else ""
            lines.append(
                f'  x{group.occurrences}  "{shown}"  first at {group.first_path}:'
                f"{group.first_line}{tag}"
            )
        remaining = len(data.literal_groups) - _TOP
        if remaining > 0:
            lines.append(f"  ... and {remaining} more values")
    lines.append(
        f"  tests excluded; thresholds: literals ≥{DEFAULT_MIN_LENGTH} chars"
        f" x>{DEFAULT_MAX_OCCURRENCES}, functions ≥{DEFAULT_MIN_STATEMENTS} statements"
        " — konpy docs predicates"
    )
    return lines


def _tool_lanes_section(data: ReportData) -> list[str]:
    lines = [_rule("External tools")]
    for lane in data.tool_lanes:
        if lane.status == "ok":
            note = f"  ({lane.note})" if lane.note else ""
            lines.append(f"  {lane.name}: {lane.findings} findings{note}")
            lines.extend(f"    {item}" for item in lane.top_items)
        else:
            suffix = f" -- {lane.note}" if lane.note else ""
            lines.append(f"  {lane.name}: {STATUS_LABEL[lane.status]}{suffix}")
    lines.append("  ruff, basedpyright, import-linter -- konpy docs cli")
    return lines


def _coverage_section(data: ReportData) -> list[str]:
    coverage = data.coverage
    scope_bits = ["non-test"]
    if data.generated_files:
        scope_bits.append("non-generated")
    if data.vendor_files:
        scope_bits.append("non-vendor")
    scope = f"{', '.join(scope_bits)} files"
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
        *_vendor_note(data),
        "",
        *_conventions_section(data),
        "",
        *_duplication_section(data),
        "",
        *_unused_section(data),
        "",
        *_tool_lanes_section(data),
        "",
        *_coverage_section(data),
        "",
        footer,
    ]
    return "\n".join(sections)


__all__ = ["render_report"]
