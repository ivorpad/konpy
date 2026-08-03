"""Tests for `konpy.core._report_render` (section order, tool-lane rendering)."""

from __future__ import annotations

import dataclasses

from konpy.core._report_render import render_report
from konpy.core._report_tools import ReportToolLane
from konpy.core.report import (
    ReportConventions,
    ReportCoverage,
    ReportData,
    ReportFunctionGroup,
    ReportLiteralGroup,
)

_CLEAN_CONVENTIONS = ReportConventions(
    status="clean",
    files_checked=1,
    errors=0,
    warnings=0,
    top_diagnostics=(),
    error_text=None,
)

_EMPTY_COVERAGE = ReportCoverage(
    module_docs=(0, 0),
    class_docs=(0, 0),
    function_docs=(0, 0),
    annotated_functions=(0, 0),
)


_DEFAULT_REPORT_DATA = ReportData(
    files=1,
    test_files=0,
    generated_files=0,
    vendor_files=0,
    vendor_roots=(),
    loc=10,
    skipped_unparsable=0,
    unused=(),
    literal_groups=(),
    function_groups=(),
    tool_lanes=(),
    coverage=_EMPTY_COVERAGE,
    conventions=_CLEAN_CONVENTIONS,
    duration_ms=1.0,
)


def _report_data(**overrides: object) -> ReportData:
    return dataclasses.replace(_DEFAULT_REPORT_DATA, **overrides)


def _section_index(output: str, title: str) -> int:
    index = output.find(f"── {title} ")
    assert index != -1, f"section {title!r} not found in output:\n{output}"
    return index


class TestSectionOrder:
    def test_conventions_then_duplication_then_unused_then_tools_then_coverage(self) -> None:
        data = _report_data()

        output = render_report(data)

        conventions = _section_index(output, "Conventions")
        duplication = _section_index(output, "Duplication")
        unused = _section_index(output, "Unused code")
        tools = _section_index(output, "External tools")
        coverage = _section_index(output, "Coverage")

        assert conventions < duplication < unused < tools < coverage


class TestDuplicationSectionOrdering:
    def test_function_groups_render_before_literal_groups(self) -> None:
        data = _report_data(
            literal_groups=(
                ReportLiteralGroup(
                    value="a repeatable literal value",
                    occurrences=3,
                    first_path="src/a.py",
                    first_line=1,
                ),
            ),
            function_groups=(
                ReportFunctionGroup(
                    name="shared",
                    statement_count=4,
                    members=(("src/a.py", 1), ("src/b.py", 1)),
                ),
            ),
        )

        output = render_report(data)

        assert output.index("Duplicate function implementations") < output.index(
            "Repeated string literals"
        )

    def test_multi_line_literal_value_renders_on_one_line(self) -> None:
        data = _report_data(
            literal_groups=(
                ReportLiteralGroup(
                    value="<form action=/upload>\n<input\ttype=file>",
                    occurrences=4,
                    first_path="src/a.py",
                    first_line=1,
                ),
            ),
        )

        output = render_report(data)

        literal_line = next(
            line for line in output.splitlines() if line.startswith("  x4  ")
        )
        assert "\\n<input\\tt" in literal_line

    def test_singular_counts_render_without_plural_s(self) -> None:
        data = _report_data(
            function_groups=(
                ReportFunctionGroup(
                    name="shared",
                    statement_count=4,
                    members=(("src/a.py", 1), ("src/b.py", 1)),
                ),
            ),
        )

        output = render_report(data)

        assert "1 duplicate-function group\n" in output
        assert "(1 group)" in output
        assert "1 file " in output.splitlines()[0]

    def test_cross_component_group_is_tagged(self) -> None:
        data = _report_data(
            function_groups=(
                ReportFunctionGroup(
                    name="shared",
                    statement_count=4,
                    members=(("src/pkg_a/a.py", 1), ("src/pkg_b/b.py", 1)),
                    is_cross_component=True,
                ),
            ),
        )

        output = render_report(data)

        assert "[cross-component]" in output

    def test_same_component_group_is_not_tagged(self) -> None:
        data = _report_data(
            function_groups=(
                ReportFunctionGroup(
                    name="shared",
                    statement_count=4,
                    members=(("src/pkg_a/a.py", 1), ("src/pkg_a/b.py", 1)),
                    is_cross_component=False,
                ),
            ),
        )

        output = render_report(data)

        assert "[cross-component]" not in output


class TestToolLanesSection:
    def test_ok_lane_renders_findings_and_indented_top_items(self) -> None:
        data = _report_data(
            tool_lanes=(
                ReportToolLane(
                    name="ruff",
                    status="ok",
                    findings=2,
                    top_items=("E501 x2  line too long",),
                    note=None,
                    duration_ms=5.0,
                ),
            ),
        )

        output = render_report(data)

        assert "  ruff: 2 findings" in output
        assert "    E501 x2  line too long" in output

    def test_not_installed_lane_renders_a_single_line(self) -> None:
        data = _report_data(
            tool_lanes=(
                ReportToolLane(
                    name="ruff",
                    status="not-installed",
                    findings=0,
                    top_items=(),
                    note='pip install "konpy[quality]"',
                    duration_ms=0.0,
                ),
            ),
        )

        output = render_report(data)

        assert '  ruff: not installed -- pip install "konpy[quality]"' in output
        # Exactly one line for this lane: no follow-on indented item lines.
        lane_line_index = output.index("ruff: not installed")
        following = output[lane_line_index:].splitlines()[1]
        assert not following.startswith("    ")

    def test_no_config_lane_renders_a_single_line(self) -> None:
        data = _report_data(
            tool_lanes=(
                ReportToolLane(
                    name="import-linter",
                    status="no-config",
                    findings=0,
                    top_items=(),
                    note="no contracts configured -- see docs/guides/import-boundaries.md",
                    duration_ms=0.0,
                ),
            ),
        )

        output = render_report(data)

        assert "  import-linter: no config -- no contracts configured" in output

    def test_timed_out_lane_renders_a_single_line(self) -> None:
        data = _report_data(
            tool_lanes=(
                ReportToolLane(
                    name="basedpyright",
                    status="timed-out",
                    findings=0,
                    top_items=(),
                    note="exceeded 60s",
                    duration_ms=60000.0,
                ),
            ),
        )

        output = render_report(data)

        assert "  basedpyright: timed out -- exceeded 60s" in output

    def test_error_lane_renders_a_single_line(self) -> None:
        data = _report_data(
            tool_lanes=(
                ReportToolLane(
                    name="ruff",
                    status="error",
                    findings=0,
                    top_items=(),
                    note="unexpected failure",
                    duration_ms=1.0,
                ),
            ),
        )

        output = render_report(data)

        assert "  ruff: error -- unexpected failure" in output
