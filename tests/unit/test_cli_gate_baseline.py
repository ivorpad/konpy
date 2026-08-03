from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import app
from konpy.cli.gate import run_gate_command
from konpy.core.filesystem import FakeFileSystem

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_config(tmp_path: Path, *, paths: str = "src/service.py") -> None:
    write_json(
        tmp_path / "konpy.json",
        {
            "version": "v1",
            "conventions": [
                {
                    "name": "service-must-export-process",
                    "paths": paths,
                    "must": {"export": ["process"]},
                }
            ],
        },
    )


def write_baseline(tmp_path: Path, entries: dict[str, dict[str, int]], *, name: str) -> None:
    write_json(tmp_path / name, {"baselineVersion": "v1", "entries": entries})


def payload_json(*, file_path: str, content: str) -> str:
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
            "cwd": "/project",
        }
    )


def invoke_gate(
    *,
    tmp_path: Path,
    stdin_text: str,
    match: list[str] | None = None,
    fail_closed: bool = False,
    baseline: str | None = None,
) -> int:
    return run_gate_command(
        match=match or [],
        config_path=None,
        config_package=None,
        diagnostic_level="warning",
        error_on_warnings=False,
        placeholder=None,
        max_diagnostics=100,
        stdin_text=stdin_text,
        file_system=FakeFileSystem(),
        fail_closed=fail_closed,
        baseline=baseline,
    )


class TestGateBaselineExemptsRecordedViolations:
    def test_rewrite_keeping_the_baselined_count_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        write_baseline(
            tmp_path,
            {"src/service.py": {"service-must-export-process": 1}},
            name="konpy.baseline.json",
        )
        monkeypatch.chdir(tmp_path)

        exit_code = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
        )

        assert exit_code == 0

    def test_new_violation_still_blocks_with_baseline_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        # Baseline covers a DIFFERENT file -- this write introduces a fresh,
        # never-recorded violation.
        write_baseline(
            tmp_path,
            {"src/other.py": {"service-must-export-process": 1}},
            name="konpy.baseline.json",
        )
        monkeypatch.chdir(tmp_path)

        exit_code = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
        )

        assert exit_code == 2

    def test_conforming_write_passes_with_baseline_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        write_baseline(
            tmp_path,
            {"src/service.py": {"service-must-export-process": 1}},
            name="konpy.baseline.json",
        )
        monkeypatch.chdir(tmp_path)

        exit_code = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(
                file_path="src/service.py",
                content="def process():\n    return 1\n",
            ),
            match=["src/**/*.py"],
        )

        assert exit_code == 0


class TestGateExplicitBaselineFlag:
    def test_explicit_baseline_path_is_used_for_reading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        write_baseline(
            tmp_path,
            {"src/service.py": {"service-must-export-process": 1}},
            name="custom.baseline.json",
        )
        monkeypatch.chdir(tmp_path)

        # Default-path baseline doesn't exist, so this would block without
        # --baseline pointing at the custom file.
        blocked = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
        )
        assert blocked == 2

        passed = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
            baseline="custom.baseline.json",
        )
        assert passed == 0


class TestGateMalformedBaseline:
    def test_fails_open_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        write_config(tmp_path)
        (tmp_path / "konpy.baseline.json").write_text("not json")
        monkeypatch.chdir(tmp_path)

        exit_code = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
        )

        assert exit_code == 0

    def test_fails_closed_when_requested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        (tmp_path / "konpy.baseline.json").write_text("not json")
        monkeypatch.chdir(tmp_path)

        exit_code = invoke_gate(
            tmp_path=tmp_path,
            stdin_text=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
            match=["src/**/*.py"],
            fail_closed=True,
        )

        assert exit_code == 2


class TestGateBaselineCliWiring:
    def test_baseline_flag_is_accepted_by_the_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_config(tmp_path)
        write_baseline(
            tmp_path,
            {"src/service.py": {"service-must-export-process": 1}},
            name="custom.baseline.json",
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["gate", "--match", "src/**/*.py", "--baseline", "custom.baseline.json"],
            input=payload_json(file_path="src/service.py", content="VALUE = 1\n"),
        )

        assert result.exit_code == 0
