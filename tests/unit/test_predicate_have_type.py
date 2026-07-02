from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.predicates.have_type import check_have_type


def context(path: str) -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="",
    )


class TestCheckHaveType:
    def test_returns_no_diagnostics_when_file_matches_expected_file(self) -> None:
        file_system = FakeFileSystem(files=["src/index.py"])

        result = check_have_type(
            expected="file",
            context=context("src/index.py"),
            file_system=file_system,
        )

        assert result == []

    def test_returns_no_diagnostics_when_directory_matches_expected_directory(self) -> None:
        file_system = FakeFileSystem(directories=["src"])

        result = check_have_type(
            expected="directory",
            context=context("src"),
            file_system=file_system,
        )

        assert result == []

    def test_returns_diagnostic_when_expected_file_but_found_directory(self) -> None:
        file_system = FakeFileSystem(directories=["src"])

        result = check_have_type(
            expected="file",
            context=context("src"),
            file_system=file_system,
        )

        assert len(result) == 1
        assert result[0].message == "Expected a file but found a directory"
        assert result[0].predicate_name == "haveType"

    def test_returns_diagnostic_when_expected_directory_but_found_file(self) -> None:
        file_system = FakeFileSystem(files=["src/index.py"])

        result = check_have_type(
            expected="directory",
            context=context("src/index.py"),
            file_system=file_system,
        )

        assert len(result) == 1
        assert result[0].message == "Expected a directory but found a file"

    def test_returns_diagnostic_when_missing_path_expected_file(self) -> None:
        result = check_have_type(
            expected="file",
            context=context("missing.py"),
            file_system=FakeFileSystem(),
        )

        assert len(result) == 1
        assert result[0].message == "Expected a file but path does not exist"

    def test_returns_diagnostic_when_missing_path_expected_directory(self) -> None:
        result = check_have_type(
            expected="directory",
            context=context("missing"),
            file_system=FakeFileSystem(),
        )

        assert len(result) == 1
        assert result[0].message == "Expected a directory but path does not exist"

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        result = check_have_type(
            expected="file",
            context=context("missing.py"),
            file_system=FakeFileSystem(),
            convention_name="test-convention",
            severity="warning",
        )

        assert result[0].convention_name == "test-convention"
        assert result[0].severity == "warning"
