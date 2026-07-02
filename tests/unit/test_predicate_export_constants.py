from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.export_constants import check_export_constants
from konsistent.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/index.py")


def context(
    placeholders: dict[str, PlaceholderValue] | None = None,
) -> PredicateContext:
    return PredicateContext(
        path="src/index.py",
        placeholders=placeholders or {},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestExportConstants:
    def test_returns_no_diagnostics_when_constant_is_exported(self) -> None:
        result = check_export_constants(
            expected=["MAX_RETRIES"],
            context=context(),
            structure=parse_source("MAX_RETRIES = 3"),
        )

        assert result == []

    def test_returns_diagnostic_when_constant_is_missing(self) -> None:
        result = check_export_constants(
            expected=["MAX_RETRIES"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export constant "MAX_RETRIES"'
        assert result[0].predicate_name == "exportConstants"
        assert result[0].file_path == "src/index.py"

    def test_missing_constant_diagnostic_includes_expected_and_fix_hint(self) -> None:
        result = check_export_constants(
            expected=["MAX_RETRIES"],
            context=context(),
            structure=parse_source(""),
        )

        assert result[0].expected == "MAX_RETRIES"
        assert result[0].fix_hint is not None
        assert "MAX_RETRIES" in result[0].fix_hint
        assert "src/index.py" in result[0].fix_hint

    def test_resolves_template_placeholders_in_constant_names(self) -> None:
        result = check_export_constants(
            expected=["${name}_LIMIT"],
            context=context({"name": PlaceholderValue("RETRY")}),
            structure=parse_source("RETRY_LIMIT = 5"),
        )

        assert result == []

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        result = check_export_constants(
            expected=["MAX_RETRIES"],
            context=context(),
            structure=parse_source(""),
            convention_name="constant-convention",
            severity="warning",
        )

        assert len(result) == 1
        assert result[0].convention_name == "constant-convention"
        assert result[0].severity == "warning"
