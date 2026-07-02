from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _write_claude_stub(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        f"print({json.dumps(payload)!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_extract_rules_uses_stub_agent_and_writes_default_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "rules.md").write_text(
        "# Rules\n\nEvery source file must be a file.\nUse ruff for formatting.\n",
        encoding="utf-8",
    )

    stub_bin = tmp_path / "bin"
    _write_claude_stub(
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
            "unmapped": [
                {
                    "rule": "Use ruff for formatting.",
                    "reason": "Formatting belongs to Ruff.",
                }
            ],
        },
    )
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    exit_code, stdout, stderr = run_cli(
        project_dir,
        "extract-rules",
        "rules.md",
        "--agent",
        "auto",
    )

    output_pack = project_dir / "packs" / "rules.json"
    assert exit_code == 0
    assert stderr == ""
    assert output_pack.exists()
    parsed = json.loads(output_pack.read_text(encoding="utf-8"))
    assert parsed["conventionSpecVersion"] == "v1"
    assert parsed["conventions"][0]["name"] == "source-files-are-files"
    assert "Wrote reusable convention proposal to" in stdout
    assert "packs/rules.json" in stdout
    assert "Unmapped rules:" in stdout
    assert "Use ruff for formatting." in stdout
    assert not (project_dir / "konsistent.json").exists()
