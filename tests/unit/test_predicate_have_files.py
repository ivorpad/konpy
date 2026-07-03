from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.core.placeholders import PlaceholderValue
from konpy.predicates.have_files import check_have_files


def context(
    *,
    path: str = "plugins/auth",
    files: list[str] | None = None,
    placeholders: dict[str, PlaceholderValue] | None = None,
) -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders=placeholders or {},
        file_system=FakeFileSystem(files=files or [], directories=["plugins/auth"]),
        base_path=path,
    )


class TestCheckHaveFiles:
    def test_returns_no_diagnostics_when_all_files_exist(self) -> None:
        result = check_have_files(
            expected=["index.py", "manifest.json"],
            context=context(files=["plugins/auth/index.py", "plugins/auth/manifest.json"]),
        )

        assert result == []

    def test_returns_diagnostic_for_each_missing_file(self) -> None:
        result = check_have_files(
            expected=["index.py", "manifest.json", "README.md"],
            context=context(files=["plugins/auth/index.py"]),
        )

        assert len(result) == 2
        assert result[0].message == "Missing required file: manifest.json"
        assert result[1].message == "Missing required file: README.md"

    def test_resolves_templates_in_file_names(self) -> None:
        result = check_have_files(
            expected=["${name.toPascalCase()}Provider.py"],
            context=context(
                files=["plugins/auth/OpenaiProvider.py"],
                placeholders={"name": PlaceholderValue("openai")},
            ),
        )

        assert result == []

    def test_reports_missing_template_resolved_file(self) -> None:
        result = check_have_files(
            expected=["${name.toPascalCase()}Provider.py"],
            context=context(placeholders={"name": PlaceholderValue("openai")}),
        )

        assert len(result) == 1
        assert result[0].message == "Missing required file: OpenaiProvider.py"

    def test_includes_convention_name_and_predicate_name(self) -> None:
        result = check_have_files(
            expected=["missing.py"],
            context=context(),
            convention_name="test-rule",
            severity="warning",
        )

        assert result[0].convention_name == "test-rule"
        assert result[0].predicate_name == "haveFiles"
        assert result[0].severity == "warning"
