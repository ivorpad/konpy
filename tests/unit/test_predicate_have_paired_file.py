from __future__ import annotations

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.core.placeholders import PlaceholderValue
from konpy.predicates.have_paired_file import check_have_paired_file


def context(
    *,
    path: str = "src/service.py",
    placeholders: dict[str, PlaceholderValue] | None = None,
) -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders=placeholders or {},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestCheckHavePairedFile:
    def test_returns_no_diagnostics_when_root_relative_paired_file_exists(self) -> None:
        file_system = FakeFileSystem(files=["tests/test_service.py"])

        result = check_have_paired_file(
            expected="tests/test_${name}.py",
            context=context(placeholders={"name": PlaceholderValue("service")}),
            file_system=file_system,
        )

        assert result == []

    def test_checks_repo_root_not_matched_file_directory(self) -> None:
        file_system = FakeFileSystem(files=["tests/test_service.py"])

        result = check_have_paired_file(
            expected="tests/test_${name}.py",
            context=context(
                path="src/package/service.py",
                placeholders={"name": PlaceholderValue("service")},
            ),
            file_system=file_system,
        )

        assert result == []

    def test_returns_diagnostic_when_paired_file_is_missing(self) -> None:
        result = check_have_paired_file(
            expected="tests/test_${name}.py",
            context=context(placeholders={"name": PlaceholderValue("service")}),
            file_system=FakeFileSystem(),
        )

        assert len(result) == 1
        assert result[0].predicate_name == "havePairedFile"
        assert result[0].message == "Missing paired file: tests/test_service.py"
        assert result[0].file_path == "src/service.py"

    def test_resolves_case_transform_templates(self) -> None:
        file_system = FakeFileSystem(files=["tests/test_openai_service.py"])

        result = check_have_paired_file(
            expected="tests/test_${name.toSnakeCase()}_service.py",
            context=context(placeholders={"name": PlaceholderValue("openai")}),
            file_system=file_system,
        )

        assert result == []

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        result = check_have_paired_file(
            expected="tests/test_${name}.py",
            context=context(placeholders={"name": PlaceholderValue("service")}),
            file_system=FakeFileSystem(),
            convention_name="paired-tests",
            severity="warning",
        )

        assert len(result) == 1
        assert result[0].convention_name == "paired-tests"
        assert result[0].severity == "warning"

    def test_missing_paired_file_diagnostic_includes_expected_and_fix_hint(self) -> None:
        result = check_have_paired_file(
            expected="tests/test_${name}.py",
            context=context(placeholders={"name": PlaceholderValue("service")}),
            file_system=FakeFileSystem(),
        )

        assert result[0].expected == "tests/test_service.py"
        assert result[0].fix_hint is not None
        assert "tests/test_service.py" in result[0].fix_hint
