from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _write_claude_stub(
    path: Path,
    *,
    verdict_payload: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        f"print({json.dumps(verdict_payload)!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _hook_payload(*, project_dir: Path, file_path: str = "src/x.py") -> str:
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
            "cwd": str(project_dir),
        }
    )


def _prepend_stub_bin_to_path(monkeypatch: pytest.MonkeyPatch, stub_bin: Path) -> None:
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}")


class TestHookLogEndToEnd:
    def test_fail_verdict_writes_jsonl_finding(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        reason = "method body does not match its docstring"
        prompt = "verify the method body matches its docstring"
        _write_claude_stub(
            stub_bin / "claude",
            verdict_payload={
                "verdict": "fail",
                "reasons": [reason],
            },
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            prompt,
            "--match",
            "src/**/*.py",
            "--log",
            "findings.jsonl",
        )

        findings_path = project_dir / "findings.jsonl"
        assert exit_code == 2
        assert stdout == ""
        assert reason in stderr
        assert findings_path.exists()

        lines = findings_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["schemaVersion"] == "v1"
        assert record["verdict"] == "fail"
        assert record["filePath"] == "src/x.py"
        assert record["prompt"] == prompt
        assert record["agent"] == "claude"

    def test_pass_verdict_does_not_create_log_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        _write_claude_stub(
            stub_bin / "claude",
            verdict_payload={
                "verdict": "pass",
                "reasons": [],
            },
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
            "--log",
            "findings.jsonl",
        )

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""
        assert not (project_dir / "findings.jsonl").exists()
