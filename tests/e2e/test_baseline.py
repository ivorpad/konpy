from __future__ import annotations

import json
from pathlib import Path

VIOLATING = "VALUE = 1\n"
CONFORMING = "def process():\n    return 1\n"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(project_dir: Path, *, paths: str = "src/*.py") -> None:
    _write_json(
        project_dir / "konpy.json",
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


def _write_payload(*, project_dir: Path, file_path: str, content: str) -> str:
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
            "cwd": str(project_dir),
        }
    )


class TestBrownfieldBaselineLoop:
    def test_full_loop(self, tmp_path: Path, run_cli) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)
        _write_file(project_dir / "src" / "a.py", VIOLATING)
        _write_file(project_dir / "src" / "b.py", VIOLATING)
        _write_file(project_dir / "src" / "c.py", VIOLATING)

        # 1. repo with 3 violations -> check exits 1
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")
        assert exit_code == 1
        assert "Found 3 errors." in stdout
        assert stderr == ""

        # 2. check --write-baseline exits 0 and writes the file
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--write-baseline")
        assert exit_code == 0
        assert "Baseline written: 3 violations across 3 files -> " in stdout
        baseline_path = project_dir / "konpy.baseline.json"
        assert baseline_path.exists()
        written = json.loads(baseline_path.read_text())
        assert written["entries"] == {
            "src/a.py": {"must-export-process": 1},
            "src/b.py": {"must-export-process": 1},
            "src/c.py": {"must-export-process": 1},
        }

        # 3. plain check (auto-discovery) exits 0 -- everything is baselined
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")
        assert exit_code == 0
        assert "No violations found, 3 baselined." in stdout

        # 4. introduce a 4th violation -> check exits 1 reporting ONLY the new one
        _write_file(project_dir / "src" / "d.py", VIOLATING)
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")
        assert exit_code == 1
        assert "src/d.py" in stdout
        assert "src/a.py" not in stdout
        assert "src/b.py" not in stdout
        assert "src/c.py" not in stdout
        assert "Found 1 error, 3 baselined." in stdout

        # 5. fix one old (already-baselined) violation. The transient 4th
        # violation is also fixed here: the baseline is a pure per-(file,
        # convention) COUNT comparison, not diagnostic-identity tracking, so
        # an unbaselined violation left live would keep `check` failing
        # regardless of what else changes -- there is no state where a
        # brand-new violation is both present and non-blocking.
        _write_file(project_dir / "src" / "a.py", CONFORMING)
        _write_file(project_dir / "src" / "d.py", CONFORMING)
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")
        assert exit_code == 0
        assert "Stale baseline entries:" in stdout
        assert (
            'Stale baseline entry for "must-export-process" in src/a.py: '
            "recorded 1, found 0. Run konpy check --write-baseline to ratchet down."
        ) in stdout

        # 6. --write-baseline again -> the floor ratchets down, no raise warning
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--write-baseline")
        assert exit_code == 0
        assert "Baseline written: 2 violations across 2 files -> " in stdout
        assert "baseline: raised" not in stdout
        assert "baseline: raised" not in stderr

        # ... and a subsequent plain check has nothing stale to report.
        exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")
        assert exit_code == 0
        assert "Stale baseline entries:" not in stdout


class TestGateRespectsBaseline:
    def test_gate_blocks_new_violation_but_passes_rewrite_keeping_baselined_count(
        self, tmp_path: Path, run_cli, run_cli_stdin
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)
        _write_file(project_dir / "src" / "service.py", VIOLATING)

        exit_code, _, _ = run_cli(project_dir, "check", "--write-baseline")
        assert exit_code == 0

        # A rewrite that keeps the same baselined violation count passes.
        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                file_path="src/service.py",
                content=VIOLATING,
            ),
            "gate",
            "--match",
            "src/**/*.py",
        )
        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""

        # A NEW violation, on a file never covered by the baseline, blocks.
        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _write_payload(
                project_dir=project_dir,
                file_path="src/other.py",
                content=VIOLATING,
            ),
            "gate",
            "--match",
            "src/**/*.py",
        )
        assert exit_code == 2
        parsed = json.loads(stderr)
        assert parsed["diagnostics"][0]["filePath"] == "src/other.py"


class TestShowBaselinedEndToEnd:
    def test_show_baselined_renders_hidden_diagnostics(
        self, tmp_path: Path, run_cli
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)
        _write_file(project_dir / "src" / "a.py", VIOLATING)

        run_cli(project_dir, "check", "--write-baseline")

        exit_code, stdout, _ = run_cli(
            project_dir, "check", "--no-colors", "--show-baselined"
        )

        assert exit_code == 0
        assert "Baselined diagnostics:" in stdout
        assert "src/a.py" in stdout
        assert 'Missing export "process"' in stdout
        assert "1 baselined" in stdout


class TestFilesScopedCheckRespectsBaseline:
    def test_files_scoped_run_hides_baselined_violation(
        self, tmp_path: Path, run_cli
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_config(project_dir)
        _write_file(project_dir / "src" / "a.py", VIOLATING)
        _write_file(project_dir / "src" / "b.py", VIOLATING)

        exit_code, _, _ = run_cli(project_dir, "check", "--write-baseline")
        assert exit_code == 0

        exit_code, _, stderr = run_cli(
            project_dir, "check", "--no-colors", "--files", "src/a.py"
        )

        assert exit_code == 0
        assert stderr == ""
