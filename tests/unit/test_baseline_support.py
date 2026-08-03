from __future__ import annotations

from pathlib import Path

from konpy.cli._baseline_support import (
    DEFAULT_BASELINE_FILENAME,
    compute_raised_entries,
    format_baseline_written_message,
    format_raised_warning,
    read_baseline_if_present,
    resolve_baseline_path,
    write_baseline_file,
)
from konpy.config.errors import Err, Ok
from konpy.core.baseline import BaselineData
from konpy.core.diagnostics import Diagnostic


def diagnostic(
    *,
    file_path: str = "src/a.py",
    convention_name: str | None = "conv-name",
    predicate_name: str = "export",
    line: int | None = 1,
    message: str = "test diagnostic",
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name=predicate_name,
        message=message,
        convention_name=convention_name,
        line=line,
    )


class TestResolveBaselinePath:
    def test_explicit_baseline_wins(self) -> None:
        path = resolve_baseline_path(baseline="custom.json", config_path="konpy.strict.json")

        assert path == Path("custom.json")

    def test_defaults_next_to_config_path(self) -> None:
        path = resolve_baseline_path(baseline=None, config_path="configs/konpy.json")

        assert path == Path("configs") / DEFAULT_BASELINE_FILENAME

    def test_defaults_to_cwd_when_no_config_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        path = resolve_baseline_path(baseline=None, config_path=None)

        assert path == tmp_path / DEFAULT_BASELINE_FILENAME


class TestReadBaselineIfPresent:
    def test_missing_file_returns_ok_none(self, tmp_path: Path) -> None:
        result = read_baseline_if_present(tmp_path / "konpy.baseline.json")

        assert isinstance(result, Ok)
        assert result.value is None

    def test_valid_file_returns_ok_baseline_data(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"
        path.write_text('{"baselineVersion": "v1", "entries": {"src/a.py": {"conv": 1}}}')

        result = read_baseline_if_present(path)

        assert isinstance(result, Ok)
        assert result.value is not None
        assert result.value.entries == {"src/a.py": {"conv": 1}}

    def test_malformed_file_returns_err_naming_the_path(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"
        path.write_text("not json")

        result = read_baseline_if_present(path)

        assert isinstance(result, Err)
        assert str(path) in result.error
        assert result.error.startswith(f"Invalid baseline ({path}):")

    def test_directory_at_path_is_treated_as_absent(self, tmp_path: Path) -> None:
        directory = tmp_path / "konpy.baseline.json"
        directory.mkdir()

        result = read_baseline_if_present(directory)

        assert isinstance(result, Ok)
        assert result.value is None


class TestComputeRaisedEntries:
    def test_no_previous_baseline_never_raises(self) -> None:
        new = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 5}})

        assert compute_raised_entries(previous=None, new=new) == []

    def test_increased_count_is_raised(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 1}})
        new = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 3}})

        raised = compute_raised_entries(previous=previous, new=new)

        assert len(raised) == 1
        assert raised[0].file_path == "src/a.py"
        assert raised[0].convention_name == "conv"
        assert raised[0].previous_count == 1
        assert raised[0].new_count == 3

    def test_brand_new_key_is_raised_from_zero(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={})
        new = BaselineData(baseline_version="v1", entries={"src/b.py": {"conv": 2}})

        raised = compute_raised_entries(previous=previous, new=new)

        assert raised == [
            type(raised[0])(
                file_path="src/b.py",
                convention_name="conv",
                previous_count=0,
                new_count=2,
            )
        ]

    def test_decreased_count_is_not_raised(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 3}})
        new = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 1}})

        assert compute_raised_entries(previous=previous, new=new) == []

    def test_unchanged_count_is_not_raised(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 2}})
        new = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 2}})

        assert compute_raised_entries(previous=previous, new=new) == []

    def test_removed_key_is_not_raised(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 2}})
        new = BaselineData(baseline_version="v1", entries={})

        assert compute_raised_entries(previous=previous, new=new) == []

    def test_results_sorted_by_file_then_convention(self) -> None:
        previous = BaselineData(baseline_version="v1", entries={})
        new = BaselineData(
            baseline_version="v1",
            entries={
                "src/b.py": {"conv": 1},
                "src/a.py": {"z-conv": 1, "a-conv": 1},
            },
        )

        raised = compute_raised_entries(previous=previous, new=new)

        assert [(entry.file_path, entry.convention_name) for entry in raised] == [
            ("src/a.py", "a-conv"),
            ("src/a.py", "z-conv"),
            ("src/b.py", "conv"),
        ]


class TestFormatRaisedWarning:
    def test_renders_file_convention_and_counts(self) -> None:
        (entry,) = compute_raised_entries(
            previous=BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 1}}),
            new=BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 4}}),
        )

        assert format_raised_warning(entry) == "baseline: raised src/a.py/conv from 1 to 4"


class TestWriteBaselineFile:
    def test_writes_a_baseline_matching_the_diagnostics(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"

        data = write_baseline_file(
            path=path,
            diagnostics=[diagnostic(file_path="src/a.py"), diagnostic(file_path="src/a.py")],
        )

        assert data.entries == {"src/a.py": {"conv-name": 2}}
        assert path.exists()
        reread = read_baseline_if_present(path)
        assert isinstance(reread, Ok)
        assert reread.value == data

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "dir" / "konpy.baseline.json"

        write_baseline_file(path=path, diagnostics=[diagnostic()])

        assert path.exists()


class TestFormatBaselineWrittenMessage:
    def test_pluralizes_violations_and_files(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"
        data = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv": 2}, "src/b.py": {"conv": 1}},
        )

        message = format_baseline_written_message(data=data, path=path)

        assert message == f"Baseline written: 3 violations across 2 files -> {path}"

    def test_singular_violation_and_file(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"
        data = BaselineData(baseline_version="v1", entries={"src/a.py": {"conv": 1}})

        message = format_baseline_written_message(data=data, path=path)

        assert message == f"Baseline written: 1 violation across 1 file -> {path}"

    def test_zero_violations(self, tmp_path: Path) -> None:
        path = tmp_path / "konpy.baseline.json"
        data = BaselineData(baseline_version="v1", entries={})

        message = format_baseline_written_message(data=data, path=path)

        assert message == f"Baseline written: 0 violations across 0 files -> {path}"
