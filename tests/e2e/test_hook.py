from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


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
                    {
                        "name": "markdown-headings",
                        "prompt": "Verify Markdown headings are useful.",
                        "match": ["docs/**/*.md"],
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


def test_rules_mode_batches_selected_rules_and_exits_two(
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
                },
                {
                    "rule": "honest-docstrings",
                    "reasons": ["The docstring claims persistence that is absent."],
                },
            ],
        },
        argv_path=argv_path,
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
    )

    assert exit_code == 2
    assert stdout == ""
    assert (
        "contextual-errors: The ValueError omits the failed operation."
        in stderr
    )
    assert (
        "honest-docstrings: The docstring claims persistence that is absent."
        in stderr
    )

    child_argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert child_argv[0] == "-p"
    assert child_argv[1:3] == ["--model", "sonnet"]
    assert "--allowedTools" in child_argv
    assert '{"hooks":{}}' in child_argv
    verifier_prompt = child_argv[-1]
    assert 'Rule "contextual-errors"' in verifier_prompt
    assert 'Rule "honest-docstrings"' in verifier_prompt
    assert 'Rule "markdown-headings"' not in verifier_prompt


def test_rules_mode_no_applicable_rule_does_not_spawn_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli_stdin,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    write_rules(project_dir / "rules.json")

    stub_bin = tmp_path / "bin"
    marker = tmp_path / "invoked"
    stub = stub_bin / "claude"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('invoked', encoding='utf-8')\n"
        'print(\'{"verdict":"pass","failures":[]}\')\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli_stdin(
        project_dir,
        hook_payload(
            project_dir=project_dir,
            file_path="assets/logo.png",
        ),
        "hook",
        "--agent",
        "claude",
        "--rules",
        "rules.json",
        "--match",
        "**/*",
    )

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert not marker.exists()


def test_single_prompt_mode_remains_compatible(
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
        "hook",
        "--agent",
        "claude",
        "--prompt",
        "Verify the method body matches its docstring.",
        "--match",
        "src/**/*.py",
    )

    assert exit_code == 2
    assert stdout == ""
    assert "method body does not match its docstring" in stderr
    assert "honest-docstrings:" not in stderr
