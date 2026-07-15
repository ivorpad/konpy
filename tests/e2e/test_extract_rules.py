from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def write_claude_stub(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        f"print({json.dumps(payload)!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_extract_rules_writes_four_lane_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "rules.md").write_text(
        "# Rules\n\n"
        "Every source file must be a file.\n"
        "Errors must contain useful context.\n"
        "Mutable defaults are forbidden.\n"
        "Rotate reviewers weekly.\n",
        encoding="utf-8",
    )

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        {
            "pack": {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "source-files-are-files",
                        "description": "Source files should be regular files.",
                        "paths": "src/*.py",
                        "must": {"haveType": "file"},
                    }
                ],
            },
            "semantic": [
                {
                    "name": "contextual-errors",
                    "prompt": "Verify that errors contain useful operation context.",
                    "match": ["src/**/*.py"],
                    "source": "Errors must contain useful context.",
                }
            ],
            "coveredElsewhere": [
                {
                    "rule": "Mutable defaults are forbidden.",
                    "tool": "ruff B006",
                    "note": "Ruff checks mutable function defaults.",
                }
            ],
            "unmapped": [
                {
                    "rule": "Rotate reviewers weekly.",
                    "reason": "This is process guidance.",
                }
            ],
        },
    )
    monkeypatch.setenv(
        "PATH",
        f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )

    exit_code, stdout, stderr = run_cli(
        project_dir,
        "extract-rules",
        "rules.md",
        "--agent",
        "auto",
    )

    pack_path = project_dir / "packs" / "rules.json"
    rules_path = project_dir / "packs" / "rules.rules.json"
    assert exit_code == 0
    assert "konpy extract-rules: extracting from rules.md" in stderr
    assert 'via "claude" --model sonnet' in stderr
    assert pack_path.exists()
    assert rules_path.exists()

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    semantic = json.loads(rules_path.read_text(encoding="utf-8"))
    assert pack["conventions"][0]["name"] == "source-files-are-files"
    assert semantic["semanticRulesSpecVersion"] == "v1"
    assert semantic["rules"][0]["name"] == "contextual-errors"

    assert "Wrote reusable convention proposal to packs/rules.json" in stdout
    assert "Wrote semantic rules to packs/rules.rules.json" in stdout
    assert "Covered by existing linters:" in stdout
    assert "ruff B006" in stdout
    assert "Unmapped rules:" in stdout
    assert "Rotate reviewers weekly." in stdout
    assert (
        "konpy hook --match '**/*.py' --rules packs/rules.rules.json "
        "--agent claude"
    ) in stdout
    assert not (project_dir / "konpy.json").exists()


def test_extract_rules_rules_output_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "rules.md").write_text("Check errors.\n", encoding="utf-8")

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        {
            "pack": {
                "conventionSpecVersion": "v1",
                "conventions": [],
            },
            "semantic": [
                {
                    "name": "contextual-errors",
                    "prompt": "Verify errors contain context.",
                    "match": ["**/*.py"],
                }
            ],
            "coveredElsewhere": [],
            "unmapped": [],
        },
    )
    monkeypatch.setenv(
        "PATH",
        f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )

    exit_code, stdout, _stderr = run_cli(
        project_dir,
        "extract-rules",
        "rules.md",
        "--agent",
        "claude",
        "--rules-output",
        "generated/semantic.json",
    )

    assert exit_code == 0
    assert (project_dir / "generated" / "semantic.json").exists()
    assert not (project_dir / "packs" / "rules.rules.json").exists()
    assert "generated/semantic.json" in stdout
