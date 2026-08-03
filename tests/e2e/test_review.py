from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from konpy.cli.app import _preprocess_argv


def write_claude_stub(
    path: Path,
    *,
    verdict_payload: dict[str, object],
    argv_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#!/usr/bin/env python3", "import json", "import sys"]
    if argv_path is not None:
        lines.append(
            f"open({str(argv_path)!r}, 'w').write(json.dumps(sys.argv[1:]))"
        )
    lines.append(f"print({json.dumps(verdict_payload)!r})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def hook_payload(*, project_dir: Path, file_path: str = "src/x.py") -> str:
    return json.dumps(
        {
            "session_id": "e2e-session",
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
            "cwd": str(project_dir),
        }
    )


def write_rules(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "semanticRulesSpecVersion": "v1",
                "rules": [
                    {
                        "name": "contextual-errors",
                        "prompt": "Verify that errors contain useful operation context.",
                        "match": ["src/**/*.py"],
                        "source": "Errors must contain useful context.",
                    },
                    {
                        "name": "honest-docstrings",
                        "prompt": "Verify that docstrings match implemented behavior.",
                        "match": ["src/**/*.py"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def prepend_stub(
    monkeypatch: pytest.MonkeyPatch,
    stub_bin: Path,
) -> None:
    monkeypatch.setenv(
        "PATH",
        f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )


def additional_context(stdout: str) -> str:
    decoded = json.loads(stdout)
    return decoded["hookSpecificOutput"]["additionalContext"]


def test_fail_verdict_exits_zero_with_findings_on_stderr_and_json_on_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    rules_path = project_dir / "rules.json"
    write_rules(rules_path)

    stub_bin = tmp_path / "bin"
    argv_path = tmp_path / "argv.json"
    write_claude_stub(
        stub_bin / "claude",
        verdict_payload={
            "verdict": "fail",
            "failures": [
                {
                    "rule": "contextual-errors",
                    "reasons": ["The ValueError omits the failed operation."],
                }
            ],
        },
        argv_path=argv_path,
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(project_dir=project_dir),
        "review",
        "--agent",
        "claude",
        "--rules",
        "rules.json",
        "--match",
        "src/**/*.py",
    )

    assert exit_code == 0
    assert (
        "contextual-errors: The ValueError omits the failed operation."
        in stderr
    )

    context = additional_context(stdout)
    assert "konpy review findings:" in context
    assert (
        "src/x.py: contextual-errors: The ValueError omits the failed operation."
        in context
    )

    child_argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert child_argv[0] == "-p"
    assert "--allowedTools" in child_argv


def test_single_prompt_mode_never_exits_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        verdict_payload={
            "verdict": "fail",
            "reasons": ["method body does not match its docstring"],
        },
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(project_dir=project_dir),
        "review",
        "--agent",
        "claude",
        "--prompt",
        "Verify the method body matches its docstring.",
        "--match",
        "src/**/*.py",
    )

    assert exit_code == 0
    assert "method body does not match its docstring" in stderr
    assert "konpy review findings:" in additional_context(stdout)


def test_agent_missing_from_path_is_advisory_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(project_dir=project_dir),
        "review",
        "--agent",
        "claude",
        "--prompt",
        "Check it.",
        "--match",
        "src/**/*.py",
    )

    assert exit_code == 0
    assert stdout == ""
    assert "konpy review: warning:" in stderr


def test_review_argv_routes_to_review_command() -> None:
    argv = ["review", "--agent", "claude", "--prompt", "Check it."]
    assert _preprocess_argv(argv) == argv
