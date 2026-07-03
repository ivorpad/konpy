from __future__ import annotations

import json
from pathlib import Path

import pytest

from konpy.cli.infer import InferReportFormat, run_infer_command
from konpy.core.filesystem import FakeFileSystem
from konpy.infer.engine import HEURISTIC_NAMES


def basic_fixture() -> FakeFileSystem:
    return FakeFileSystem(
        contents={
            "src/services/user_service.py": "class UserService:\n    pass\n",
            "src/services/order_service.py": "class OrderService:\n    pass\n",
            "src/services/billing_service.py": "class BillingService:\n    pass\n",
            "src/services/__init__.py": "",
        }
    )


def call(*, file_system=None, **overrides) -> tuple[int, dict]:
    defaults = dict(
        include=None,
        exclude=None,
        test_glob=None,
        min_confidence=0.9,
        min_support=3,
        max_violators=10,
        heuristic=None,
        format=InferReportFormat.TEXT,
        output_path=None,
        report_path=None,
    )
    defaults.update(overrides)
    if file_system is None:
        file_system = basic_fixture()
    return run_infer_command(file_system=file_system, **defaults)


class TestRunInferCommand:
    def test_default_stdout_is_pack_stderr_is_report(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = call()

        assert exit_code == 0
        captured = capsys.readouterr()
        pack = json.loads(captured.out)
        assert pack["conventionSpecVersion"] == "v1"
        assert "Proposals" in captured.err or "No conventions proposed" in captured.err

    def test_output_path_writes_file_and_prints_confirmation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        output = tmp_path / "konpy.infer.json"

        exit_code = call(output_path=str(output))

        assert exit_code == 0
        captured = capsys.readouterr()
        assert f"Wrote proposed pack to {output}" in captured.out
        assert "Proposals" in captured.err or "No conventions proposed" in captured.err

        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["conventionSpecVersion"] == "v1"

    def test_report_path_writes_file_and_prints_confirmation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = tmp_path / "report.txt"

        exit_code = call(report_path=str(report))

        assert exit_code == 0
        captured = capsys.readouterr()
        assert f"Wrote infer report to {report}" in captured.err
        assert "Proposals" not in captured.err
        assert report.exists()

    def test_format_json_produces_valid_json_report(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = call(format=InferReportFormat.JSON)

        assert exit_code == 0
        captured = capsys.readouterr()
        report = json.loads(captured.err)
        assert set(report.keys()) == {
            "filesScanned",
            "testFilesExcluded",
            "filesSkippedUnparsable",
            "filesSkippedUnreadable",
            "proposals",
            "skipped",
        }

    def test_min_confidence_out_of_bounds_errors(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for bad in (1.5, -0.1):
            exit_code = call(min_confidence=bad)
            assert exit_code == 1
            captured = capsys.readouterr()
            assert "--min-confidence must be between 0.0 and 1.0 inclusive." in captured.err
            assert captured.out == ""

    def test_min_support_below_one_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = call(min_support=0)

        assert exit_code == 1
        assert "--min-support must be at least 1." in capsys.readouterr().err

    def test_max_violators_negative_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = call(max_violators=-1)

        assert exit_code == 1
        assert "--max-violators must be zero or greater." in capsys.readouterr().err

    def test_unknown_heuristic_errors_and_lists_valid_names(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = call(heuristic=["bogus-name"])

        assert exit_code == 1
        message = capsys.readouterr().err
        assert "Unknown --heuristic value(s): bogus-name." in message
        for name in HEURISTIC_NAMES:
            assert name in message

    def test_heuristic_filter_limits_emitted_conventions(self) -> None:
        exit_code = call(heuristic=["export-suffix"], min_confidence=0.5, min_support=1)
        assert exit_code == 0

    def test_heuristic_filter_output_only_contains_selected_heuristic(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        call(heuristic=["export-suffix"])
        pack = json.loads(capsys.readouterr().out)
        for convention in pack["conventions"]:
            assert convention["name"].startswith("infer-export-suffix-")

    def test_unwritable_output_path_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        output = blocker / "konpy.infer.json"

        exit_code = call(output_path=str(output))

        assert exit_code == 1
        assert "Could not write proposed pack" in capsys.readouterr().err

    def test_include_matching_nothing_is_a_clean_empty_run(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = call(file_system=FakeFileSystem(), include=["nope/**/*.py"])

        assert exit_code == 0
        captured = capsys.readouterr()
        pack = json.loads(captured.out)
        assert pack == {"conventionSpecVersion": "v1", "conventions": []}
        assert "Scanned 0 files" in captured.err
