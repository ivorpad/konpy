from __future__ import annotations

import json
import sys
from pathlib import Path


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _three_step_config() -> dict[str, object]:
    return {
        "version": "v1",
        "conventions": [],
        "verify": {
            "steps": [
                {"name": "ok-step", "run": [sys.executable, "-c", "print('hi')"]},
                {
                    "name": "fail-step",
                    "run": [sys.executable, "-c", "import sys; sys.exit(3)"],
                },
                {"name": "missing-tool", "run": ["definitely-not-a-real-executable-xyz"]},
            ]
        },
    }


class TestVerifyThreeStepFixture:
    def test_all_three_lines_and_summary_with_exit_1(
        self, tmp_path: Path, run_cli
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_json(project_dir / "konpy.json", _three_step_config())

        exit_code, stdout, stderr = run_cli(project_dir, "verify")

        assert exit_code == 1
        assert "[verify] ok-step ... ok" in stdout
        assert "[verify] fail-step ... FAILED" in stdout
        assert "[verify]   exit code 3" in stdout
        assert "[verify] missing-tool ... FAILED" in stdout
        assert "[verify]   executable not found" in stdout
        assert "[verify] FAILED: fail-step, missing-tool" in stdout
        assert stderr == ""


class TestVerifyAllGreen:
    def test_all_green_roster_exits_zero(self, tmp_path: Path, run_cli) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_json(
            project_dir / "konpy.json",
            {
                "version": "v1",
                "conventions": [],
                "verify": {
                    "steps": [
                        {"name": "a", "run": [sys.executable, "-c", "pass"]},
                        {"name": "b", "run": [sys.executable, "-c", "pass"]},
                    ]
                },
            },
        )

        exit_code, stdout, stderr = run_cli(project_dir, "verify")

        assert exit_code == 0
        assert "[verify] a ... ok" in stdout
        assert "[verify] b ... ok" in stdout
        assert "FAILED" not in stdout
        assert stderr == ""


class TestVerifyNoSection:
    def test_missing_verify_section_prints_pointer_and_exits_1(
        self, tmp_path: Path, run_cli
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_json(project_dir / "konpy.json", {"version": "v1", "conventions": []})

        exit_code, stdout, stderr = run_cli(project_dir, "verify")

        assert exit_code == 1
        assert stdout == ""
        assert "No verify section in" in stderr
        assert "konpy.json" in stderr
        assert "konpy docs cli" in stderr


class TestVerifyConfigErrors:
    def test_missing_config_file_errors_like_other_commands(
        self, tmp_path: Path, run_cli
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        exit_code, stdout, stderr = run_cli(project_dir, "verify")

        assert exit_code == 1
        assert stdout == ""
        assert "Could not read config file" in stderr

    def test_invalid_config_errors_like_other_commands(self, tmp_path: Path, run_cli) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_json(project_dir / "konpy.json", {"version": "v1"})

        exit_code, _stdout, stderr = run_cli(project_dir, "verify")

        assert exit_code == 1
        assert "Invalid config" in stderr


class TestVerifyRunsFromConfigDir:
    def test_roster_cwd_is_the_config_files_directory(self, tmp_path: Path, run_cli) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        sub_dir = project_dir / "sub"
        sub_dir.mkdir()
        _write_json(
            project_dir / "konpy.json",
            {
                "version": "v1",
                "conventions": [],
                "verify": {
                    "steps": [
                        {
                            "name": "write-marker",
                            "run": [
                                sys.executable,
                                "-c",
                                "open('marker.txt', 'w').close()",
                            ],
                        }
                    ]
                },
            },
        )

        exit_code, stdout, _stderr = run_cli(
            sub_dir, "verify", "--config-path", "../konpy.json"
        )

        assert exit_code == 0
        assert "[verify] write-marker ... ok" in stdout
        assert (project_dir / "marker.txt").is_file()
        assert not (sub_dir / "marker.txt").is_file()


class TestVerifyEnvironment:
    def test_konpy_verify_active_is_set_for_steps(self, tmp_path: Path, run_cli) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_json(
            project_dir / "konpy.json",
            {
                "version": "v1",
                "conventions": [],
                "verify": {
                    "steps": [
                        {
                            "name": "check-env",
                            "run": [
                                sys.executable,
                                "-c",
                                "import os, sys; "
                                "sys.exit(0 if os.environ.get('KONPY_VERIFY_ACTIVE') "
                                "== '1' else 1)",
                            ],
                        }
                    ]
                },
            },
        )

        exit_code, stdout, _stderr = run_cli(project_dir, "verify")

        assert exit_code == 0
        assert "[verify] check-env ... ok" in stdout
