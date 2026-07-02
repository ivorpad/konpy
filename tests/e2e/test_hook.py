from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _write_claude_stub(
    path: Path,
    *,
    verdict_payload: dict[str, object] | None = None,
    exit_code: int = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#!/usr/bin/env python3"]
    if verdict_payload is not None:
        lines.append(f"print({json.dumps(verdict_payload)!r})")
    if exit_code:
        lines.append("import sys")
        lines.append(f"sys.exit({exit_code})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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


class TestHookEndToEnd:
    def test_fail_verdict_stub_exits_two_with_reason_on_stderr(
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
                "verdict": "fail",
                "reasons": ["method body does not match its docstring"],
            },
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 2
        assert "method body does not match its docstring" in stderr
        assert _stdout == ""

    def test_pass_verdict_stub_exits_zero(
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
            verdict_payload={"verdict": "pass", "reasons": []},
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        assert stderr == ""
        assert _stdout == ""

    def test_stub_exiting_nonzero_exits_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        _write_claude_stub(stub_bin / "claude", exit_code=3)
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 1
        assert 'exited with code 3' in stderr

    def test_non_matching_path_never_invokes_stub_and_exits_zero(
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
            verdict_payload={"verdict": "fail", "reasons": ["should never run"]},
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir, file_path="docs/readme.md"),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        assert stderr == ""

    def test_sentinel_env_short_circuits_without_invoking_stub(
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
            verdict_payload={"verdict": "fail", "reasons": ["should never run"]},
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)
        monkeypatch.setenv("KONSISTENT_HOOK_ACTIVE", "1")

        exit_code, _stdout, stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify the method body matches its docstring",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        assert stderr == ""


class TestModelArgvEndToEnd:
    def test_child_argv_carries_default_model_sonnet_and_recursion_guards(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        argv_dump = tmp_path / "argv.json"
        stub = stub_bin / "claude"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"open({str(argv_dump)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
            'print(json.dumps({"verdict": "pass", "reasons": []}))\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, _stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify it",
            "--match",
            "src/**/*.py",
        )

        assert exit_code == 0
        child_argv = json.loads(argv_dump.read_text(encoding="utf-8"))
        assert child_argv[0] == "-p"
        assert child_argv[1:3] == ["--model", "sonnet"]
        assert "--allowedTools" in child_argv
        assert '{"hooks":{}}' in child_argv

    def test_child_argv_carries_explicit_model_override(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli_stdin,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        argv_dump = tmp_path / "argv.json"
        stub = stub_bin / "claude"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"open({str(argv_dump)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
            'print(json.dumps({"verdict": "pass", "reasons": []}))\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, _stderr = run_cli_stdin(
            project_dir,
            _hook_payload(project_dir=project_dir),
            "hook",
            "--agent",
            "claude",
            "--prompt",
            "verify it",
            "--match",
            "src/**/*.py",
            "--model",
            "claude-opus-4-8",
        )

        assert exit_code == 0
        child_argv = json.loads(argv_dump.read_text(encoding="utf-8"))
        assert child_argv[1:3] == ["--model", "claude-opus-4-8"]
