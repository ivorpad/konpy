from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def write_claude_stub(
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


def hook_payload(*, project_dir: Path) -> str:
    return json.dumps(
        {
            "session_id": "log-session",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py"},
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
                        "prompt": "Verify errors contain useful operation context.",
                        "match": ["src/**/*.py"],
                    },
                    {
                        "name": "honest-docstrings",
                        "prompt": "Verify docstrings match implemented behavior.",
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


def test_rules_failure_logs_one_record_per_failed_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_rules(project_dir / "rules.json")

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        verdict_payload={
            "verdict": "fail",
            "failures": [
                {
                    "rule": "contextual-errors",
                    "reasons": ["Missing operation context."],
                },
                {
                    "rule": "honest-docstrings",
                    "reasons": ["Docstring overstates behavior."],
                },
            ],
        },
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(project_dir=project_dir),
        "hook",
        "--agent",
        "claude",
        "--rules",
        "rules.json",
        "--match",
        "src/**/*.py",
        "--log",
        "findings.jsonl",
    )

    log_path = project_dir / "findings.jsonl"
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]

    assert exit_code == 2
    assert stdout == ""
    assert "contextual-errors: Missing operation context." in stderr
    assert "honest-docstrings: Docstring overstates behavior." in stderr
    assert len(records) == 2

    assert records[0]["rule"] == "contextual-errors"
    assert (
        records[0]["prompt"]
        == "Verify errors contain useful operation context."
    )
    assert records[0]["reasons"] == ["Missing operation context."]
    assert records[0]["sessionId"] == "log-session"

    assert records[1]["rule"] == "honest-docstrings"
    assert (
        records[1]["prompt"]
        == "Verify docstrings match implemented behavior."
    )
    assert records[1]["reasons"] == ["Docstring overstates behavior."]


def test_rules_pass_does_not_create_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_rules(project_dir / "rules.json")

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        verdict_payload={
            "verdict": "pass",
            "failures": [],
        },
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(project_dir=project_dir),
        "hook",
        "--agent",
        "claude",
        "--rules",
        "rules.json",
        "--match",
        "src/**/*.py",
        "--log",
        "findings.jsonl",
    )

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert not (project_dir / "findings.jsonl").exists()
