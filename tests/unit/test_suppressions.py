from __future__ import annotations

from konpy.core.diagnostics import Diagnostic
from konpy.core.suppressions import (
    SuppressionComment,
    filter_suppressed_diagnostics,
    parse_suppressions_for_source,
)


def diagnostic(
    *,
    file_path: str = "src/service.py",
    rule: str = "rule-a",
    line: int | None = 2,
    severity: str = "error",
    message: str = "test diagnostic",
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name="predicateName",
        message=message,
        severity=severity,
        convention_name=rule,
        line=line,
    )


class TestParseSuppressions:
    def test_parses_line_suppression_with_multiple_rules_and_reason(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[rule-a, rule-b] -- legacy API\n",
        )

        assert result.diagnostics == []
        assert result.suppressions == [
            SuppressionComment(
                file_path="src/service.py",
                line=1,
                kind="ignore",
                rules=("rule-a", "rule-b"),
                reason="legacy API",
                raw="# konpy: ignore[rule-a, rule-b] -- legacy API",
            )
        ]

    def test_parses_inline_trailing_comment(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="value = call()  # konpy: ignore[rule-a] -- accepted\n",
        )

        assert result.diagnostics == []
        assert len(result.suppressions) == 1
        assert result.suppressions[0].line == 1
        assert result.suppressions[0].kind == "ignore"
        assert result.suppressions[0].reason == "accepted"

    def test_parses_file_suppression_before_first_code_line(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source=(
                "# generated file\n"
                "\n"
                "# konpy: ignore-file[rule-a] -- generated\n"
                "VALUE = 1\n"
            ),
        )

        assert result.diagnostics == []
        assert result.suppressions == [
            SuppressionComment(
                file_path="src/service.py",
                line=3,
                kind="ignore-file",
                rules=("rule-a",),
                reason="generated",
                raw="# konpy: ignore-file[rule-a] -- generated",
            )
        ]

    def test_rejects_missing_bracketed_rule_list(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore\n",
        )

        assert result.suppressions == []
        assert [item.message for item in result.diagnostics] == [
            "Invalid suppression comment: bracketed rule list is required"
        ]
        assert result.diagnostics[0].severity == "warning"
        assert result.diagnostics[0].convention_name == "suppressions"

    def test_rejects_empty_rule_list(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[]\n",
        )

        assert result.suppressions == []
        assert [item.message for item in result.diagnostics] == [
            "Invalid suppression comment: bracketed rule list is required"
        ]

    def test_rejects_invalid_rule_names(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[RuleName, valid-rule]\n",
        )

        assert result.suppressions == []
        assert [item.message for item in result.diagnostics] == [
            'Invalid suppression rule name "RuleName"'
        ]

    def test_rejects_file_level_suppression_after_first_code_line(self) -> None:
        result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="VALUE = 1\n# konpy: ignore-file[rule-a]\n",
        )

        assert result.suppressions == []
        assert [item.message for item in result.diagnostics] == [
            'File-level suppression for "rule-a" must appear before the first code line'
        ]


class TestFilterSuppressions:
    def test_line_suppression_matches_same_line_diagnostic(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="bad_call()  # konpy: ignore[rule-a] -- local exception\n",
        )
        result = filter_suppressed_diagnostics(
            diagnostics=[diagnostic(line=1, rule="rule-a")],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a"},
            report_hygiene=True,
        )

        assert result.diagnostics == []
        assert result.hygiene_diagnostics == []
        assert len(result.suppressed) == 1
        assert result.suppressed[0].suppression.line == 1
        assert result.suppressed[0].suppression.reason == "local exception"

    def test_line_suppression_matches_immediately_above_diagnostic(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[rule-a]\ndef bad():\n    pass\n",
        )
        result = filter_suppressed_diagnostics(
            diagnostics=[diagnostic(line=2, rule="rule-a")],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a"},
            report_hygiene=True,
        )

        assert result.diagnostics == []
        assert len(result.suppressed) == 1
        assert result.suppressed[0].suppression.kind == "ignore"

    def test_line_suppression_does_not_skip_blank_lines(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[rule-a]\n\ndef bad():\n    pass\n",
        )
        original = diagnostic(line=3, rule="rule-a")

        result = filter_suppressed_diagnostics(
            diagnostics=[original],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a"},
            report_hygiene=False,
        )

        assert result.diagnostics == [original]
        assert result.suppressed == []

    def test_line_suppression_does_not_suppress_file_level_diagnostic(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[rule-a]\n",
        )
        original = diagnostic(line=None, rule="rule-a")

        result = filter_suppressed_diagnostics(
            diagnostics=[original],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a"},
            report_hygiene=False,
        )

        assert result.diagnostics == [original]
        assert result.suppressed == []

    def test_file_suppression_suppresses_file_level_and_line_level_diagnostics(
        self,
    ) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore-file[rule-a] -- generated\nVALUE = 1\n",
        )
        file_level = diagnostic(line=None, rule="rule-a", message="file-level")
        line_level = diagnostic(line=2, rule="rule-a", message="line-level")

        result = filter_suppressed_diagnostics(
            diagnostics=[file_level, line_level],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a"},
            report_hygiene=True,
        )

        assert result.diagnostics == []
        assert result.hygiene_diagnostics == []
        assert [item.diagnostic.message for item in result.suppressed] == [
            "file-level",
            "line-level",
        ]
        assert all(item.suppression.kind == "ignore-file" for item in result.suppressed)

    def test_suppression_matches_convention_name_not_predicate_name(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[have-type]\n",
        )
        original = Diagnostic(
            file_path="src/service.py",
            predicate_name="have-type",
            message="test diagnostic",
            severity="error",
            convention_name="source-files",
            line=2,
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[original],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"source-files", "have-type"},
            report_hygiene=False,
        )

        assert result.diagnostics == [original]
        assert result.suppressed == []

    def test_warning_diagnostics_are_suppressible(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[unused-code]\ndef legacy():\n    return 1\n",
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[diagnostic(line=2, rule="unused-code", severity="warning")],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"unused-code"},
            report_hygiene=True,
        )

        assert result.diagnostics == []
        assert len(result.suppressed) == 1
        assert result.suppressed[0].diagnostic.severity == "warning"

    def test_tracks_usage_per_rule_for_multi_rule_comments(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[rule-a, rule-b]\ndef bad():\n    pass\n",
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[diagnostic(line=2, rule="rule-a")],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"rule-a", "rule-b"},
            report_hygiene=True,
        )

        assert result.diagnostics == []
        assert len(result.suppressed) == 1
        assert [item.message for item in result.hygiene_diagnostics] == [
            'Unused suppression for "rule-b"'
        ]

    def test_reports_unknown_and_unused_suppressions(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[unknown-rule, known-rule]\n",
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"known-rule"},
            report_hygiene=True,
        )

        assert [item.message for item in result.hygiene_diagnostics] == [
            'Unknown suppression rule "unknown-rule"',
            'Unused suppression for "known-rule"',
        ]

    def test_report_hygiene_false_omits_parse_unknown_and_unused_warnings(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore[known-rule]\n# konpy: ignore\n",
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names={"known-rule"},
            report_hygiene=False,
        )

        assert result.diagnostics == []
        assert result.suppressed == []
        assert result.hygiene_diagnostics == []

    def test_parse_diagnostics_are_returned_as_hygiene_warnings(self) -> None:
        parse_result = parse_suppressions_for_source(
            file_path="src/service.py",
            source="# konpy: ignore\n",
        )

        result = filter_suppressed_diagnostics(
            diagnostics=[],
            suppressions_by_file={"src/service.py": parse_result.suppressions},
            parse_diagnostics=parse_result.diagnostics,
            known_rule_names=set(),
            report_hygiene=True,
        )

        assert [item.message for item in result.hygiene_diagnostics] == [
            "Invalid suppression comment: bracketed rule list is required"
        ]
