from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_empty_config(project_dir: Path) -> None:
    _write_json(project_dir / "konpy.json", {"version": "v1", "conventions": []})


def _write_payload(*, project_dir: Path, file_path: str = "src/service.py", content: str) -> str:
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": file_path,
                "content": content,
            },
            "cwd": str(project_dir),
        }
    )


class TestGateRuffEndToEnd:
    def test_ruff_finding_blocks_with_ruff_convention_name(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content="import os\n\n\ndef f():\n    return 1\n",
            ),
            "gate",
            "--match",
            "src/**/*.py",
            "--ruff",
        )

        parsed = json.loads(stderr)
        diagnostic = parsed["diagnostics"][0]

        assert exit_code == 2
        assert stdout == ""
        assert diagnostic["filePath"] == "src/service.py"
        assert diagnostic["conventionName"] == "ruff"
        assert diagnostic["predicateName"] == "F401"
        assert "unused" in diagnostic["message"]
        assert parsed["summary"]["errors"] == 1

    def test_ruff_clean_content_exits_zero_silently(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content=(
                    '"""Service module."""\n\n\n'
                    'def process() -> int:\n    """Return one."""\n    return 1\n'
                ),
            ),
            "gate",
            "--match",
            "src/**/*.py",
            "--ruff",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""

    def test_without_ruff_flag_ruff_findings_are_not_checked(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content="import os\n\n\ndef f():\n    return 1\n",
            ),
            "gate",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""


class TestGateRuffMissingBinary:
    def test_default_mode_fails_open_with_warning(
        self,
        tmp_path: Path,
        run_cli_stdin,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)
        monkeypatch.setenv("PATH", str(empty_bin))

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content="import os\n\n\ndef f():\n    return 1\n",
            ),
            "gate",
            "--match",
            "src/**/*.py",
            "--ruff",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == "konpy gate: warning: ruff not found on PATH (required by --ruff)\n"

    def test_fail_closed_blocks_with_verification_unavailable(
        self,
        tmp_path: Path,
        run_cli_stdin,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)
        monkeypatch.setenv("PATH", str(empty_bin))

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content="import os\n\n\ndef f():\n    return 1\n",
            ),
            "gate",
            "--match",
            "src/**/*.py",
            "--ruff",
            "--fail-closed",
        )

        assert exit_code == 2
        assert stdout == ""
        assert stderr.startswith("konpy gate: verification unavailable: ruff not found on PATH")
        assert stderr.rstrip("\n").endswith("(blocking: --fail-closed)")

    def test_missing_ruff_does_not_affect_non_python_matches(
        self,
        tmp_path: Path,
        run_cli_stdin,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`--ruff` only matters for `.py` overlay targets; a non-`.py` write
        is unaffected by a missing `ruff` executable, fail-open or closed."""
        empty_bin = tmp_path / "empty-bin"
        empty_bin.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_empty_config(project_dir)
        monkeypatch.setenv("PATH", str(empty_bin))

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                file_path="README.md",
                content="# hello\n",
            ),
            "gate",
            "--match",
            "**/*.md",
            "--ruff",
            "--fail-closed",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""
