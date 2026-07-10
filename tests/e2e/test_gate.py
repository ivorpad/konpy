from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_config(project_dir: Path) -> None:
    _write_json(
        project_dir / "konpy.json",
        {
            "version": "v1",
            "conventions": [
                {
                    "name": "service-must-export-process",
                    "paths": "src/service.py",
                    "must": {"export": ["process"]},
                }
            ],
        },
    )


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


class TestGateEndToEnd:
    def test_broken_write_exits_two_with_json_diagnostics(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(project_dir=project_dir, content="VALUE = 1\n"),
            "gate",
            "--match",
            "src/**/*.py",
        )

        parsed = json.loads(stderr)
        diagnostic = parsed["diagnostics"][0]

        assert exit_code == 2
        assert stdout == ""
        assert diagnostic["filePath"] == "src/service.py"
        assert diagnostic["conventionName"] == "service-must-export-process"
        assert diagnostic["predicateName"] == "export"
        assert diagnostic["message"] == 'Missing export "process"'
        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 0
        assert parsed["truncation"] == {"shown": 1, "omitted": 0}

    def test_conforming_write_exits_zero_silently(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                content="def process():\n    return 1\n",
            ),
            "gate",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""

    def test_unmatched_path_exits_zero_silently(
        self,
        tmp_path: Path,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(project_dir=project_dir, content="VALUE = 1\n"),
            "gate",
            "--match",
            "tests/**/*.py",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""
