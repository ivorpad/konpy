from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from konpy.cli.app import app

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_file(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_export_config(tmp_path: Path, *, paths: str = "src/*.py") -> None:
    write_json(
        tmp_path / "konpy.json",
        {
            "version": "v1",
            "conventions": [
                {
                    "name": "must-export-process",
                    "paths": paths,
                    "must": {"export": ["process"]},
                }
            ],
        },
    )


def write_violating_file(tmp_path: Path, name: str) -> None:
    write_file(tmp_path / "src" / name, "VALUE = 1\n")


def write_conforming_file(tmp_path: Path, name: str) -> None:
    write_file(tmp_path / "src" / name, "def process():\n    return 1\n")


class TestWriteBaseline:
    def test_writes_baseline_and_exits_zero_with_confirmation(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        write_violating_file(tmp_path, "b.py")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--write-baseline"])

        assert result.exit_code == 0
        assert "Baseline written: 2 violations across 2 files -> " in result.output
        baseline_path = tmp_path / "konpy.baseline.json"
        assert baseline_path.exists()
        data = json.loads(baseline_path.read_text())
        assert data["entries"] == {
            "src/a.py": {"must-export-process": 1},
            "src/b.py": {"must-export-process": 1},
        }

    def test_write_baseline_exits_zero_even_though_violations_exist(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)

        # Without --write-baseline this same project fails.
        assert runner.invoke(app, ["check"]).exit_code == 1

        result = runner.invoke(app, ["check", "--write-baseline"])
        assert result.exit_code == 0

    def test_explicit_baseline_flag_controls_the_write_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["check", "--write-baseline", "--baseline", "custom.baseline.json"]
        )

        assert result.exit_code == 0
        assert not (tmp_path / "konpy.baseline.json").exists()
        assert (tmp_path / "custom.baseline.json").exists()

    def test_raised_count_prints_loud_warning(self, tmp_path: Path, monkeypatch) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        # A brand-new violation, never recorded before, is a raise from 0.
        write_violating_file(tmp_path, "c.py")

        result = runner.invoke(app, ["check", "--write-baseline"])

        assert result.exit_code == 0
        assert "baseline: raised src/c.py/must-export-process from 0 to 1" in result.output

    def test_first_write_baseline_never_reports_raised(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--write-baseline"])

        assert result.exit_code == 0
        assert "baseline: raised" not in result.output


class TestAutoDiscovery:
    def test_plain_check_reads_default_baseline_next_to_config(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        result = runner.invoke(app, ["check"])

        assert result.exit_code == 0

    def test_new_unbaselined_violation_still_fails(self, tmp_path: Path, monkeypatch) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        write_violating_file(tmp_path, "b.py")
        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 1
        assert "src/b.py" in result.output
        assert "src/a.py" not in result.output

    def test_explicit_baseline_flag_used_for_reading_too(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline", "--baseline", "custom.baseline.json"])

        # Default-path check still fails: no konpy.baseline.json was written.
        assert runner.invoke(app, ["check"]).exit_code == 1

        result = runner.invoke(app, ["check", "--baseline", "custom.baseline.json"])
        assert result.exit_code == 0


class TestMalformedBaseline:
    def test_malformed_baseline_is_a_hard_error_on_read(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        (tmp_path / "konpy.baseline.json").write_text("not json")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check"])

        assert result.exit_code == 1
        assert "Invalid baseline" in result.output

    def test_malformed_baseline_also_blocks_write_baseline(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        (tmp_path / "konpy.baseline.json").write_text("not json")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--write-baseline"])

        assert result.exit_code == 1
        assert "Invalid baseline" in result.output


class TestShowBaselined:
    def test_show_baselined_renders_hidden_diagnostics(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        result = runner.invoke(app, ["check", "--no-colors", "--show-baselined"])

        assert result.exit_code == 0
        assert "Baselined diagnostics:" in result.output
        assert "src/a.py" in result.output
        assert "1 baselined" in result.output

    def test_baselined_hidden_by_default(self, tmp_path: Path, monkeypatch) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        result = runner.invoke(app, ["check", "--no-colors"])

        assert "Baselined diagnostics:" not in result.output
        assert "1 baselined" in result.output


class TestJsonOutput:
    def test_json_output_carries_baselined_and_baseline_stale_keys(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        # Fix the baselined violation so its recorded count goes stale.
        write_conforming_file(tmp_path, "a.py")

        result = runner.invoke(app, ["check", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["baselined"] == []
        assert parsed["summary"]["baselined"] == 0
        assert parsed["baselineStale"] == [
            {
                "filePath": "src/a.py",
                "conventionName": "must-export-process",
                "recorded": 1,
                "found": 0,
            }
        ]

    def test_json_baselined_array_populated_when_diagnostics_are_hidden(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        write_export_config(tmp_path)
        write_violating_file(tmp_path, "a.py")
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["check", "--write-baseline"])

        result = runner.invoke(app, ["check", "--format", "json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["summary"]["baselined"] == 1
        assert len(parsed["baselined"]) == 1
        assert parsed["baselined"][0]["filePath"] == "src/a.py"
        assert parsed["baselineStale"] == []
