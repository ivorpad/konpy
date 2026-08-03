from __future__ import annotations

import json

from konpy.core.baseline import BaselinedDiagnostic, BaselineStaleEntry
from konpy.core.diagnostics import Diagnostic
from konpy.core.reporters import (
    count_severities,
    format_default,
    format_github,
    format_json,
    format_markdown,
    resolve_format,
)
from konpy.core.runner import RunResult
from konpy.core.suppressions import AppliedSuppression, SuppressedDiagnostic


def make_result(
    diagnostics: list[Diagnostic],
    *,
    files_checked: int = 1,
    duration_ms: float | None = 5,
    suppressed_diagnostics: list[SuppressedDiagnostic] | None = None,
    baselined_diagnostics: list[BaselinedDiagnostic] | None = None,
    baseline_stale_entries: list[BaselineStaleEntry] | None = None,
) -> RunResult:
    return RunResult(
        diagnostics=diagnostics,
        files_checked=files_checked,
        duration_ms=duration_ms,
        suppressed_diagnostics=suppressed_diagnostics or [],
        baselined_diagnostics=baselined_diagnostics or [],
        baseline_stale_entries=baseline_stale_entries or [],
    )


def diagnostic(
    *,
    file_path: str = "src/foo.py",
    predicate_name: str = "haveType",
    message: str = "test message",
    severity: str = "error",
    convention_name: str | None = None,
    line: int | None = None,
    column: int | None = None,
    description: str | None = None,
    hint: str | None = None,
    expected: str | None = None,
    found: str | None = None,
    fix_hint: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name=predicate_name,
        message=message,
        severity=severity,
        convention_name=convention_name,
        line=line,
        column=column,
        description=description,
        hint=hint,
        expected=expected,
        found=found,
        fix_hint=fix_hint,
    )


def suppressed_diagnostic(
    *,
    file_path: str = "src/foo.py",
    predicate_name: str = "unusedCode.dead",
    message: str = 'Unused definition "legacy" is never referenced',
    severity: str = "warning",
    convention_name: str = "unused-code",
    line: int | None = 4,
    suppression_line: int = 3,
    suppression_kind: str = "ignore",
    reason: str | None = "legacy API",
) -> SuppressedDiagnostic:
    return SuppressedDiagnostic(
        diagnostic=diagnostic(
            file_path=file_path,
            predicate_name=predicate_name,
            message=message,
            severity=severity,
            convention_name=convention_name,
            line=line,
        ),
        suppression=AppliedSuppression(
            file_path=file_path,
            line=suppression_line,
            kind=suppression_kind,
            rule=convention_name,
            reason=reason,
        ),
    )


def baselined_diagnostic(
    *,
    file_path: str = "src/foo.py",
    predicate_name: str = "export",
    message: str = 'Missing export "process"',
    severity: str = "error",
    convention_name: str = "conv-name",
    line: int | None = None,
) -> BaselinedDiagnostic:
    return BaselinedDiagnostic(
        diagnostic=diagnostic(
            file_path=file_path,
            predicate_name=predicate_name,
            message=message,
            severity=severity,
            convention_name=convention_name,
            line=line,
        ),
        file_path=file_path,
        convention_name=convention_name,
    )


def stale_baseline_entry(
    *,
    file_path: str = "src/foo.py",
    convention_name: str = "conv-name",
    recorded_count: int = 2,
    found_count: int = 1,
) -> BaselineStaleEntry:
    return BaselineStaleEntry(
        file_path=file_path,
        convention_name=convention_name,
        recorded_count=recorded_count,
        found_count=found_count,
    )


class TestFormatDefault:
    def test_returns_summary_for_no_diagnostics(self) -> None:
        output = format_default(
            make_result([], files_checked=3, duration_ms=5),
            colors=False,
        )

        assert "Checked 3 files in 5ms." in output
        assert "No violations found." in output

    def test_formats_diagnostics_grouped_by_file(self) -> None:
        diagnostics = [
            diagnostic(
                file_path="src/foo.py",
                message="Expected a file but found a directory",
            ),
            diagnostic(file_path="src/foo.py", message="Another issue"),
            diagnostic(file_path="src/bar.py", message="Expected a directory"),
        ]

        output = format_default(
            make_result(diagnostics, files_checked=2, duration_ms=10),
            colors=False,
        )

        assert "src/foo.py" in output
        assert "src/bar.py" in output
        assert "Expected a file but found a directory" in output
        assert "Checked 2 files in 10ms. Found 3 errors." in output

    def test_uses_dash_for_file_level_diagnostic(self) -> None:
        output = format_default(
            make_result([diagnostic(message="file-level issue")]),
            colors=False,
        )

        assert "  -  error  file-level issue" in output

    def test_uses_line_number_when_provided(self) -> None:
        output = format_default(
            make_result([diagnostic(message="line issue", line=42)]),
            colors=False,
        )

        assert "  42  error  line issue" in output

    def test_shows_convention_name_when_present(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(
                        message="Missing export",
                        convention_name="provider-packages",
                    )
                ]
            ),
            colors=False,
        )

        assert "Missing export  [provider-packages]" in output

    def test_omits_convention_name_when_absent(self) -> None:
        output = format_default(
            make_result([diagnostic(message="Some problem")]),
            colors=False,
        )

        line = next(line for line in output.splitlines() if "Some problem" in line)
        assert "[" not in line

    def test_sorts_file_level_violations_before_line_specific_ones(self) -> None:
        diagnostics = [
            diagnostic(message="line 10 issue", line=10),
            diagnostic(message="file-level issue"),
            diagnostic(message="line 5 issue", line=5),
        ]

        output = format_default(make_result(diagnostics), colors=False)
        lines = [line for line in output.splitlines() if "issue" in line]

        assert "file-level issue" in lines[0]
        assert "line 5 issue" in lines[1]
        assert "line 10 issue" in lines[2]

    def test_right_aligns_line_numbers_to_widest_in_group(self) -> None:
        diagnostics = [
            diagnostic(message="issue at 5", line=5),
            diagnostic(message="issue at 100", line=100),
        ]

        output = format_default(make_result(diagnostics), colors=False)

        assert "    5  error  issue at 5" in output
        assert "  100  error  issue at 100" in output

    def test_pads_dash_to_match_widest_line_number(self) -> None:
        diagnostics = [
            diagnostic(message="file-level"),
            diagnostic(message="at line 999", line=999),
        ]

        output = format_default(make_result(diagnostics), colors=False)

        assert "    -  error  file-level" in output
        assert "  999  error  at line 999" in output

    def test_separates_file_groups_with_blank_lines(self) -> None:
        diagnostics = [
            diagnostic(file_path="src/a.py", message="problem a"),
            diagnostic(file_path="src/b.py", message="problem b"),
        ]

        output = format_default(make_result(diagnostics), colors=False)
        lines = output.splitlines()
        index = next(index for index, line in enumerate(lines) if "problem a" in line)

        assert lines[index + 1] == ""

    def test_renders_root_path_as_project_root(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(
                        file_path=".",
                        predicate_name="haveFiles",
                        message="Missing required file: README.md",
                    )
                ]
            ),
            colors=False,
        )

        assert "(project root)" in output
        assert ".\n" not in output

    def test_uses_singular_for_one_error(self) -> None:
        output = format_default(
            make_result([diagnostic(message="err1")], files_checked=1),
            colors=False,
        )

        assert "Checked 1 file in 5ms. Found 1 error." in output

    def test_uses_plural_for_multiple_errors(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(file_path="a.py", message="err1"),
                    diagnostic(file_path="b.py", message="err2"),
                ],
                files_checked=2,
                duration_ms=3,
            ),
            colors=False,
        )

        assert "Checked 2 files in 3ms. Found 2 errors." in output

    def test_warning_only_summary(self) -> None:
        output = format_default(
            make_result(
                [diagnostic(severity="warning", message="test warning")],
                files_checked=1,
            ),
            colors=False,
        )

        assert "  -  warning  test warning" in output
        assert "Found 1 warning." in output

    def test_mixed_summary(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(file_path="src/foo.py", message="test error"),
                    diagnostic(
                        file_path="src/bar.py",
                        severity="warning",
                        message="test warning 1",
                    ),
                    diagnostic(
                        file_path="src/baz.py",
                        severity="warning",
                        message="test warning 2",
                    ),
                ],
                files_checked=3,
            ),
            colors=False,
        )

        assert "Found 1 error and 2 warnings." in output

    def test_suppressed_only_summary_mentions_unsuppressed_and_suppressed_count(
        self,
    ) -> None:
        output = format_default(
            make_result(
                [],
                files_checked=3,
                suppressed_diagnostics=[suppressed_diagnostic()],
            ),
            colors=False,
        )

        assert (
            "Checked 3 files in 5ms. No unsuppressed violations found. "
            "Suppressed 1 finding."
        ) in output

    def test_mixed_summary_mentions_suppressed_count(self) -> None:
        output = format_default(
            make_result(
                [diagnostic(message="visible error")],
                files_checked=2,
                suppressed_diagnostics=[
                    suppressed_diagnostic(),
                    suppressed_diagnostic(message='Definition "old" is only referenced by tests'),
                ],
            ),
            colors=False,
        )

        assert "Checked 2 files in 5ms. Found 1 error. Suppressed 2 findings." in output

    def test_show_suppressed_lists_suppressed_diagnostics_with_reason(self) -> None:
        output = format_default(
            make_result(
                [],
                suppressed_diagnostics=[
                    suppressed_diagnostic(
                        file_path="src/service.py",
                        message='Definition "legacy" is only referenced by tests',
                        line=4,
                        suppression_line=3,
                        reason="legacy API",
                    )
                ],
            ),
            colors=False,
            show_suppressed=True,
        )

        assert "Suppressed diagnostics:" in output
        assert "src/service.py" in output
        assert (
            '4  suppressed warning  Definition "legacy" is only referenced by tests  '
            "[unused-code]  (suppressed by line 3: legacy API)"
        ) in output

    def test_suppressed_diagnostics_are_not_listed_without_show_suppressed(self) -> None:
        output = format_default(
            make_result(
                [],
                suppressed_diagnostics=[
                    suppressed_diagnostic(message='Definition "legacy" is only referenced by tests')
                ],
            ),
            colors=False,
        )

        assert "Suppressed diagnostics:" not in output
        assert 'Definition "legacy" is only referenced by tests' not in output
        assert "Suppressed 1 finding." in output

    def test_colors_disabled_has_no_ansi_codes(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(
                        message="Missing export",
                        convention_name="provider-packages",
                        line=5,
                    )
                ]
            ),
            colors=False,
        )

        assert "\x1b[" not in output

    def test_colors_enabled_has_ansi_codes(self) -> None:
        output = format_default(
            make_result([diagnostic(message="Missing export")]),
            colors=True,
        )

        assert "\x1b[" in output


class TestFormatDefaultBaseline:
    def test_baselined_summary_mentions_count(self) -> None:
        output = format_default(
            make_result(
                [],
                files_checked=3,
                baselined_diagnostics=[baselined_diagnostic()],
            ),
            colors=False,
        )

        assert "Checked 3 files in 5ms. No violations found, 1 baselined." in output

    def test_mixed_summary_mentions_baselined_count(self) -> None:
        output = format_default(
            make_result(
                [diagnostic(message="visible error")],
                baselined_diagnostics=[baselined_diagnostic(), baselined_diagnostic()],
            ),
            colors=False,
        )

        assert "Checked 1 file in 5ms. Found 1 error, 2 baselined." in output

    def test_show_baselined_lists_baselined_diagnostics(self) -> None:
        output = format_default(
            make_result(
                [],
                baselined_diagnostics=[
                    baselined_diagnostic(
                        file_path="src/service.py",
                        message='Missing export "process"',
                        convention_name="documented-service",
                    )
                ],
            ),
            colors=False,
            show_baselined=True,
        )

        assert "Baselined diagnostics:" in output
        assert "src/service.py" in output
        assert 'error  Missing export "process"  [documented-service]' in output

    def test_baselined_diagnostics_not_listed_without_show_baselined(self) -> None:
        output = format_default(
            make_result(
                [],
                baselined_diagnostics=[baselined_diagnostic(message='Missing export "process"')],
            ),
            colors=False,
        )

        assert "Baselined diagnostics:" not in output
        assert 'Missing export "process"' not in output
        assert "1 baselined" in output

    def test_stale_entries_render_unconditionally_as_warnings(self) -> None:
        output = format_default(
            make_result(
                [],
                baseline_stale_entries=[
                    stale_baseline_entry(
                        file_path="src/service.py",
                        convention_name="documented-service",
                        recorded_count=2,
                        found_count=1,
                    )
                ],
            ),
            colors=False,
        )

        assert "Stale baseline entries:" in output
        assert (
            'Stale baseline entry for "documented-service" in src/service.py: '
            "recorded 2, found 1. Run konpy check --write-baseline to ratchet down."
        ) in output


class TestFormatDefaultFixHints:
    def test_appends_hint_line_when_fix_hint_present(self) -> None:
        output = format_default(
            make_result(
                [diagnostic(message="Missing X", fix_hint="Add X")],
            ),
            colors=False,
        )

        lines = output.splitlines()
        message_index = next(i for i, line in enumerate(lines) if "Missing X" in line)
        hint_line = lines[message_index + 1]
        assert "->" in hint_line
        assert "fix: Add X" in hint_line

    def test_no_hint_line_when_all_three_absent(self) -> None:
        output = format_default(
            make_result([diagnostic()]),
            colors=False,
        )

        assert "->" not in output

    def test_hint_line_combines_expected_and_found_and_fix(self) -> None:
        output = format_default(
            make_result(
                [
                    diagnostic(
                        message="Bad thing",
                        expected="Foo",
                        found="Bar",
                        fix_hint="Do X",
                    )
                ],
            ),
            colors=False,
        )

        lines = output.splitlines()
        hint_line = next(line for line in lines if "->" in line)
        assert hint_line.count("expected: ") == 1
        assert hint_line.count("found: ") == 1
        assert hint_line.count("fix: ") == 1
        assert "expected: Foo" in hint_line
        assert "found: Bar" in hint_line
        assert "fix: Do X" in hint_line


class TestFormatJson:
    def test_returns_valid_json(self) -> None:
        output = format_json(make_result([diagnostic(message="Some problem")]))

        assert json.loads(output)["diagnostics"][0]["message"] == "Some problem"

    def test_returns_object_for_no_diagnostics(self) -> None:
        assert json.loads(format_json(make_result([]))) == {
            "diagnostics": [],
            "suppressed": [],
            "baselined": [],
            "baselineStale": [],
            "summary": {
                "filesChecked": 1,
                "errors": 0,
                "warnings": 0,
                "suppressed": 0,
                "baselined": 0,
                "durationMs": 5,
            },
            "truncation": {
                "shown": 0,
                "omitted": 0,
            },
        }

    def test_outputs_camel_case_fields_for_line_diagnostic(self) -> None:
        output = format_json(
            make_result(
                [
                    diagnostic(
                        predicate_name="exportInterfaces",
                        message="Missing interface",
                        convention_name="provider-interface",
                        line=3,
                        column=5,
                    )
                ]
            )
        )

        assert json.loads(output)["diagnostics"] == [
            {
                "severity": "error",
                "conventionName": "provider-interface",
                "filePath": "src/foo.py",
                "predicateName": "exportInterfaces",
                "message": "Missing interface",
                "line": 3,
            }
        ]

    def test_omits_line_for_file_level_diagnostic(self) -> None:
        parsed = json.loads(format_json(make_result([diagnostic()])))

        assert "line" not in parsed["diagnostics"][0]

    def test_omits_column_from_json_output(self) -> None:
        parsed = json.loads(
            format_json(make_result([diagnostic(line=10, column=5)]))
        )

        assert "column" not in parsed["diagnostics"][0]

    def test_outputs_warning_severity(self) -> None:
        parsed = json.loads(
            format_json(make_result([diagnostic(severity="warning")]))
        )

        assert parsed["diagnostics"][0]["severity"] == "warning"

    def test_outputs_suppressed_array_and_summary_count(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [diagnostic(message="visible")],
                    files_checked=4,
                    suppressed_diagnostics=[
                        suppressed_diagnostic(
                            file_path="src/service.py",
                            message='Definition "legacy" is only referenced by tests',
                            line=4,
                            suppression_line=3,
                            reason="legacy API",
                        )
                    ],
                )
            )
        )

        assert parsed["summary"] == {
            "filesChecked": 4,
            "errors": 1,
            "warnings": 0,
            "suppressed": 1,
            "baselined": 0,
            "durationMs": 5,
        }
        assert parsed["suppressed"] == [
            {
                "severity": "warning",
                "conventionName": "unused-code",
                "filePath": "src/service.py",
                "predicateName": "unusedCode.dead",
                "message": 'Definition "legacy" is only referenced by tests',
                "line": 4,
                "suppressedBy": {
                    "kind": "ignore",
                    "filePath": "src/service.py",
                    "line": 3,
                    "reason": "legacy API",
                },
            }
        ]

    def test_outputs_suppressed_details_even_when_show_suppressed_is_false(self) -> None:
        parsed = json.loads(
            format_json(
                make_result([], suppressed_diagnostics=[suppressed_diagnostic()]),
                show_suppressed=False,
            )
        )

        assert len(parsed["suppressed"]) == 1


class TestFormatJsonBaseline:
    def test_outputs_baselined_array_and_summary_count(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [diagnostic(message="visible")],
                    files_checked=4,
                    baselined_diagnostics=[
                        baselined_diagnostic(
                            file_path="src/service.py",
                            message='Missing export "process"',
                            convention_name="documented-service",
                        )
                    ],
                )
            )
        )

        assert parsed["summary"]["baselined"] == 1
        assert parsed["baselined"] == [
            {
                "severity": "error",
                "conventionName": "documented-service",
                "filePath": "src/service.py",
                "predicateName": "export",
                "message": 'Missing export "process"',
            }
        ]

    def test_outputs_baselined_details_even_when_show_baselined_is_false(self) -> None:
        parsed = json.loads(
            format_json(
                make_result([], baselined_diagnostics=[baselined_diagnostic()]),
                show_baselined=False,
            )
        )

        assert len(parsed["baselined"]) == 1

    def test_outputs_baseline_stale_entries(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [],
                    baseline_stale_entries=[
                        stale_baseline_entry(
                            file_path="src/service.py",
                            convention_name="documented-service",
                            recorded_count=2,
                            found_count=1,
                        )
                    ],
                )
            )
        )

        assert parsed["baselineStale"] == [
            {
                "filePath": "src/service.py",
                "conventionName": "documented-service",
                "recorded": 2,
                "found": 1,
            }
        ]

    def test_baselined_and_baseline_stale_are_empty_by_default(self) -> None:
        parsed = json.loads(format_json(make_result([diagnostic()])))

        assert parsed["baselined"] == []
        assert parsed["baselineStale"] == []
        assert parsed["summary"]["baselined"] == 0


class TestFormatJsonTruncation:
    def test_truncation_key_present_and_zero_when_nothing_truncated(self) -> None:
        parsed = json.loads(
            format_json(make_result([diagnostic(message="only one")]))
        )

        assert parsed["truncation"] == {"shown": 1, "omitted": 0}

    def test_truncation_reports_shown_and_omitted(self) -> None:
        truncated_result = make_result([diagnostic(message="shown")])

        parsed = json.loads(format_json(truncated_result, omitted=3))

        assert parsed["truncation"] == {"shown": 1, "omitted": 3}
        assert len(parsed["diagnostics"]) == 1

    def test_total_errors_and_warnings_override_summary_when_truncated(self) -> None:
        truncated_result = make_result([diagnostic(message="shown", severity="error")])

        parsed = json.loads(
            format_json(
                truncated_result,
                total_errors=5,
                total_warnings=2,
                omitted=4,
            )
        )

        assert parsed["summary"]["errors"] == 5
        assert parsed["summary"]["warnings"] == 2
        assert parsed["truncation"] == {"shown": 1, "omitted": 4}

    def test_summary_falls_back_to_counting_diagnostics_without_totals(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [
                        diagnostic(message="e1", severity="error"),
                        diagnostic(message="w1", severity="warning"),
                    ]
                )
            )
        )

        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 1


class TestFormatJsonFixHints:
    def test_includes_expected_found_fix_hint_when_present(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [diagnostic(expected="Foo", found="Bar", fix_hint="Do X")],
                )
            )
        )

        item = parsed["diagnostics"][0]
        assert item["expected"] == "Foo"
        assert item["found"] == "Bar"
        assert item["fixHint"] == "Do X"

    def test_omits_expected_found_fix_hint_when_none(self) -> None:
        parsed = json.loads(format_json(make_result([diagnostic()])))

        item = parsed["diagnostics"][0]
        assert "expected" not in item
        assert "found" not in item
        assert "fixHint" not in item
        assert "description" not in item
        assert "hint" not in item

    def test_omits_only_the_absent_subset(self) -> None:
        parsed = json.loads(
            format_json(make_result([diagnostic(fix_hint="Do X")]))
        )

        item = parsed["diagnostics"][0]
        assert "expected" not in item
        assert "found" not in item
        assert item["fixHint"] == "Do X"

    def test_includes_description_and_hint_when_present(self) -> None:
        parsed = json.loads(
            format_json(
                make_result(
                    [diagnostic(description="Why this matters", hint="A helpful nudge")]
                )
            )
        )

        item = parsed["diagnostics"][0]
        assert item["description"] == "Why this matters"
        assert item["hint"] == "A helpful nudge"


class TestFormatGithub:
    def test_returns_empty_string_for_no_diagnostics(self) -> None:
        assert format_github(make_result([])) == ""

    def test_formats_file_level_violation_without_line_parameter(self) -> None:
        output = format_github(
            make_result(
                [
                    diagnostic(
                        file_path="packages/openai/src/index.py",
                        predicate_name="export",
                        message='Missing export "openai"',
                        convention_name="provider-packages",
                    )
                ]
            )
        )

        assert output == (
            "::error file=packages/openai/src/index.py,"
            'title=provider-packages::Missing export "openai"'
        )

    def test_includes_line_parameter_for_line_specific_violations(self) -> None:
        output = format_github(
            make_result(
                [
                    diagnostic(
                        file_path="packages/openai/src/provider.py",
                        predicate_name="exportInterfaces",
                        message="Recommended interface missing",
                        convention_name="iface-convention",
                        severity="warning",
                        line=7,
                    )
                ]
            )
        )

        assert output == (
            "::warning file=packages/openai/src/provider.py,line=7,"
            "title=iface-convention::Recommended interface missing"
        )

    def test_omits_column_even_when_present(self) -> None:
        output = format_github(make_result([diagnostic(line=10, column=5)]))

        assert "col=" not in output
        assert "column=" not in output
        assert output == "::error file=src/foo.py,line=10::test message"

    def test_omits_title_when_convention_name_is_absent(self) -> None:
        output = format_github(make_result([diagnostic(message="Some problem")]))

        assert output == "::error file=src/foo.py::Some problem"

    def test_joins_multiple_diagnostics_with_newlines(self) -> None:
        output = format_github(
            make_result(
                [
                    diagnostic(
                        file_path="src/a.py",
                        message="problem a",
                        convention_name="conv-a",
                    ),
                    diagnostic(
                        file_path="src/b.py",
                        message="problem b",
                        convention_name="conv-b",
                        line=5,
                    ),
                ]
            )
        )

        assert output.splitlines() == [
            "::error file=src/a.py,title=conv-a::problem a",
            "::error file=src/b.py,line=5,title=conv-b::problem b",
        ]

    def test_suppressed_notices_are_omitted_without_show_suppressed(self) -> None:
        output = format_github(
            make_result([], suppressed_diagnostics=[suppressed_diagnostic()])
        )

        assert output == ""

    def test_suppressed_notices_are_emitted_with_show_suppressed(self) -> None:
        output = format_github(
            make_result(
                [],
                suppressed_diagnostics=[
                    suppressed_diagnostic(
                        file_path="src/service.py",
                        message='Definition "legacy" is only referenced by tests',
                        line=4,
                        suppression_line=3,
                        reason="legacy API",
                    )
                ],
            ),
            show_suppressed=True,
        )

        assert output == (
            "::notice file=src/service.py,line=4,title=Suppressed unused-code::"
            'warning: Definition "legacy" is only referenced by tests '
            "(suppressed by line 3: legacy API)"
        )

    def test_baselined_notices_are_omitted_without_show_baselined(self) -> None:
        output = format_github(make_result([], baselined_diagnostics=[baselined_diagnostic()]))

        assert output == ""

    def test_baselined_notices_are_emitted_with_show_baselined(self) -> None:
        output = format_github(
            make_result(
                [],
                baselined_diagnostics=[
                    baselined_diagnostic(
                        file_path="src/service.py",
                        message='Missing export "process"',
                        convention_name="documented-service",
                        line=4,
                    )
                ],
            ),
            show_baselined=True,
        )

        assert output == (
            "::notice file=src/service.py,line=4,title=Baselined documented-service::"
            'error: Missing export "process"'
        )

    def test_stale_entries_render_as_warning_notices_unconditionally(self) -> None:
        output = format_github(
            make_result(
                [],
                baseline_stale_entries=[
                    stale_baseline_entry(
                        file_path="src/service.py",
                        convention_name="documented-service",
                        recorded_count=2,
                        found_count=1,
                    )
                ],
            )
        )

        assert output == (
            "::warning title=Stale baseline entry::"
            'Stale baseline entry for "documented-service" in src/service.py: '
            "recorded 2, found 1. Run konpy check --write-baseline to ratchet down."
        )


class TestFormatMarkdown:
    def test_returns_summary_for_no_diagnostics(self) -> None:
        output = format_markdown(make_result([], files_checked=5, duration_ms=3))

        assert output == "**Checked 5 files in 3ms. No violations found.**"

    def test_formats_diagnostics_as_markdown_tables_grouped_by_file(self) -> None:
        diagnostics = [
            diagnostic(
                file_path="packages/openai/src/index.py",
                predicate_name="export",
                message='Missing export "openai"',
                convention_name="provider-packages",
            ),
            diagnostic(
                file_path="packages/openai/src/provider.py",
                predicate_name="exportInterfaces",
                message='Interface "Provider" must extend "Base"',
                convention_name="provider-interface",
                line=3,
            ),
        ]

        output = format_markdown(
            make_result(diagnostics, files_checked=2, duration_ms=8)
        )

        assert "**`packages/openai/src/index.py`**" in output
        assert "**`packages/openai/src/provider.py`**" in output
        assert "| Line | Severity | Message | Convention |" in output
        assert '| - | error | Missing export "openai" | provider-packages |' in output
        assert (
            '| 3 | error | Interface "Provider" must extend "Base" | '
            "provider-interface |"
        ) in output
        assert "**Checked 2 files in 8ms. Found 2 errors.**" in output

    def test_uses_dash_for_file_level_violations(self) -> None:
        output = format_markdown(
            make_result([diagnostic(message="file-level issue")])
        )

        assert "| - | error | file-level issue |  |" in output

    def test_uses_line_number_when_provided(self) -> None:
        output = format_markdown(make_result([diagnostic(message="line issue", line=42)]))

        assert "| 42 | error | line issue |  |" in output

    def test_lists_file_level_violations_before_line_specific_ones(self) -> None:
        diagnostics = [
            diagnostic(message="line 10 issue", line=10),
            diagnostic(message="file-level issue"),
            diagnostic(message="line 5 issue", line=5),
        ]

        output = format_markdown(make_result(diagnostics))
        rows = [
            line
            for line in output.splitlines()
            if line.startswith("|")
            and not line.startswith("| Line")
            and not line.startswith("|--")
        ]

        assert "file-level issue" in rows[0]
        assert "line 5 issue" in rows[1]
        assert "line 10 issue" in rows[2]

    def test_shows_empty_convention_column_when_absent(self) -> None:
        output = format_markdown(make_result([diagnostic(message="Some problem")]))

        assert "| - | error | Some problem |  |" in output

    def test_separates_file_groups_with_blank_lines(self) -> None:
        diagnostics = [
            diagnostic(file_path="src/a.py", message="problem a"),
            diagnostic(file_path="src/b.py", message="problem b"),
        ]

        output = format_markdown(make_result(diagnostics))

        assert "|  |\n\n**`src/b.py`**" in output

    def test_renders_root_path_as_project_root(self) -> None:
        output = format_markdown(
            make_result([diagnostic(file_path=".", message="Missing README")])
        )

        assert "**`(project root)`**" in output

    def test_warning_rows_and_summary(self) -> None:
        output = format_markdown(
            make_result(
                [
                    diagnostic(
                        severity="warning",
                        message="Missing recommended file",
                        convention_name="should-have-readme",
                    )
                ]
            )
        )

        assert (
            "| - | warning | Missing recommended file | should-have-readme |"
            in output
        )
        assert "Found 1 warning.**" in output

    def test_mixed_summary(self) -> None:
        output = format_markdown(
            make_result(
                [
                    diagnostic(file_path="src/a.py", message="critical"),
                    diagnostic(
                        file_path="src/b.py",
                        severity="warning",
                        message="minor",
                    ),
                ],
                files_checked=2,
            )
        )

        assert "Found 1 error and 1 warning.**" in output

    def test_suppressed_only_summary_mentions_suppressed_count(self) -> None:
        output = format_markdown(
            make_result(
                [],
                files_checked=3,
                suppressed_diagnostics=[suppressed_diagnostic()],
            )
        )

        assert output == (
            "**Checked 3 files in 5ms. No unsuppressed violations found. "
            "Suppressed 1 finding.**"
        )

    def test_show_suppressed_adds_suppressed_markdown_section(self) -> None:
        output = format_markdown(
            make_result(
                [],
                suppressed_diagnostics=[
                    suppressed_diagnostic(
                        file_path="src/service.py",
                        message='Definition "legacy" is only referenced by tests',
                        line=4,
                        suppression_line=3,
                        reason="legacy API",
                    )
                ],
            ),
            show_suppressed=True,
        )

        assert "### Suppressed diagnostics" in output
        assert "**`src/service.py`**" in output
        assert "| Line | Severity | Message | Convention | Suppressed By | Reason |" in output
        assert (
            '| 4 | warning | Definition "legacy" is only referenced by tests | '
            "unused-code | line 3 | legacy API |"
        ) in output
        assert (
            "**Checked 1 file in 5ms. No unsuppressed violations found. "
            "Suppressed 1 finding.**"
        ) in output

    def test_mixed_markdown_summary_mentions_suppressed_count(self) -> None:
        output = format_markdown(
            make_result(
                [diagnostic(file_path="src/a.py", message="critical")],
                files_checked=2,
                suppressed_diagnostics=[suppressed_diagnostic()],
            )
        )

        assert "**Checked 2 files in 5ms. Found 1 error. Suppressed 1 finding.**" in output

    def test_show_baselined_adds_baselined_markdown_section(self) -> None:
        output = format_markdown(
            make_result(
                [],
                baselined_diagnostics=[
                    baselined_diagnostic(
                        file_path="src/service.py",
                        message='Missing export "process"',
                        convention_name="documented-service",
                    )
                ],
            ),
            show_baselined=True,
        )

        assert "### Baselined diagnostics" in output
        assert "**`src/service.py`**" in output
        assert (
            '| - | error | Missing export "process" | documented-service |'
        ) in output

    def test_baselined_summary_mentions_count(self) -> None:
        output = format_markdown(
            make_result(
                [diagnostic(file_path="src/a.py", message="critical")],
                files_checked=2,
                baselined_diagnostics=[baselined_diagnostic()],
            )
        )

        assert "**Checked 2 files in 5ms. Found 1 error, 1 baselined.**" in output

    def test_stale_entries_render_unconditionally(self) -> None:
        output = format_markdown(
            make_result(
                [],
                baseline_stale_entries=[
                    stale_baseline_entry(
                        file_path="src/service.py",
                        convention_name="documented-service",
                        recorded_count=2,
                        found_count=1,
                    )
                ],
            )
        )

        assert "### Stale baseline entries" in output
        assert (
            '- Stale baseline entry for "documented-service" in src/service.py: '
            "recorded 2, found 1. Run konpy check --write-baseline to ratchet down."
        ) in output


class TestFormatMarkdownFixHints:
    def test_message_cell_gets_html_suffix_when_hint_present(self) -> None:
        output = format_markdown(
            make_result([diagnostic(message="Missing X", fix_hint="Add X")])
        )

        assert "<br><sub>fix: Add X</sub>" in output

    def test_message_cell_unchanged_when_hint_absent(self) -> None:
        output = format_markdown(make_result([diagnostic(message="Missing X")]))

        assert "<br>" not in output
        assert "| Missing X |" in output


class TestCountSeverities:
    def test_counts_errors_and_warnings_separately(self) -> None:
        errors, warnings = count_severities(
            [
                diagnostic(severity="error"),
                diagnostic(severity="warning"),
                diagnostic(severity="warning"),
            ]
        )

        assert (errors, warnings) == (1, 2)

    def test_returns_zeros_for_no_diagnostics(self) -> None:
        assert count_severities([]) == (0, 0)


class TestResolveFormat:
    def test_returns_explicit_format_when_not_default(self) -> None:
        assert resolve_format(format="json") == "json"
        assert resolve_format(format="github") == "github"
        assert resolve_format(format="markdown") == "markdown"

    def test_returns_github_when_github_actions_is_true(self) -> None:
        assert resolve_format(
            format="default",
            env={"GITHUB_ACTIONS": "true"},
        ) == "github"

    def test_returns_default_when_github_actions_is_not_true(self) -> None:
        assert resolve_format(format="default", env={}) == "default"
        assert resolve_format(
            format="default",
            env={"GITHUB_ACTIONS": "false"},
        ) == "default"
