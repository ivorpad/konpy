from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from konpy.cli._hook_findings import HookFinding


def _write_claude_stub(
    path: Path,
    *,
    payload: dict[str, object] | None = None,
    exit_code: int = 0,
    marker_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#!/usr/bin/env python3"]
    if marker_path is not None:
        lines.append("from pathlib import Path")
        lines.append(f"Path({str(marker_path)!r}).write_text('invoked\\n', encoding='utf-8')")
    if payload is not None:
        lines.append(f"print({json.dumps(payload)!r})")
    if exit_code:
        lines.append("import sys")
        lines.append(f"sys.exit({exit_code})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def _prepend_stub_bin_to_path(monkeypatch: pytest.MonkeyPatch, stub_bin: Path) -> None:
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}")


def _seed_findings(path: Path) -> None:
    prompt = "verify service modules export matching service classes"
    findings = [
        HookFinding(
            filePath="src/user_service.py",
            prompt=prompt,
            agent="claude",
            model="sonnet",
            reasons=["expected UserService export was missing"],
        ),
        HookFinding(
            filePath="src/order_service.py",
            prompt=prompt,
            agent="claude",
            model="sonnet",
            reasons=["expected OrderService export was missing"],
        ),
    ]
    path.write_text(
        "".join(f"{finding.model_dump_json(exclude_none=True)}\n" for finding in findings),
        encoding="utf-8",
    )


class TestHookProposeEndToEnd:
    def test_hook_propose_uses_stub_agent_and_writes_default_pack(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _seed_findings(project_dir / "findings.jsonl")

        stub_bin = tmp_path / "bin"
        _write_claude_stub(
            stub_bin / "claude",
            payload={
                "pack": {
                    "conventionSpecVersion": "v1",
                    "conventions": [
                        {
                            "name": "service-modules-export-matching-class",
                            "description": "Service modules export the matching Service class.",
                            "paths": "src/{name}_service.py",
                            "must": {
                                "exportClasses": ["${name.toPascalCase()}Service"]
                            },
                        }
                    ],
                },
                "unmapped": [
                    {
                        "rule": "Semantic service behavior review",
                        "reason": "Requires human judgment.",
                    }
                ],
            },
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, stdout, stderr = run_cli(
            project_dir,
            "hook-propose",
            "findings.jsonl",
            "--agent",
            "claude",
        )

        output_pack = project_dir / "packs" / "hook-proposals.json"
        assert exit_code == 0
        assert stderr == ""
        assert output_pack.exists()
        parsed = json.loads(output_pack.read_text(encoding="utf-8"))
        assert parsed["conventionSpecVersion"] == "v1"
        assert parsed["conventions"][0]["name"] == "service-modules-export-matching-class"
        assert "Wrote reusable convention proposal to" in stdout
        assert "packs/hook-proposals.json" in stdout
        assert "Unmapped rules:" in stdout
        assert "Semantic service behavior review" in stdout
        assert not (project_dir / "konpy.json").exists()

    def test_hook_propose_invalid_pack_exits_one_and_writes_no_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _seed_findings(project_dir / "findings.jsonl")

        stub_bin = tmp_path / "bin"
        _write_claude_stub(
            stub_bin / "claude",
            payload={
                "pack": {
                    "conventionSpecVersion": "v1",
                    "conventions": [
                        {
                            "name": "invalid-proposal",
                            "description": "Missing must and mustNot.",
                            "paths": "src/*.py",
                        }
                    ],
                },
                "unmapped": [],
            },
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, _stdout, stderr = run_cli(
            project_dir,
            "hook-propose",
            "findings.jsonl",
            "--agent",
            "claude",
        )

        assert exit_code == 1
        assert "Invalid proposed reusable-convention package:" in stderr
        assert not (project_dir / "packs" / "hook-proposals.json").exists()

    def test_hook_propose_missing_findings_exits_zero_without_invoking_agent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_cli,
    ) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        stub_bin = tmp_path / "bin"
        marker_path = tmp_path / "claude-invoked.txt"
        _write_claude_stub(
            stub_bin / "claude",
            exit_code=99,
            marker_path=marker_path,
        )
        _prepend_stub_bin_to_path(monkeypatch, stub_bin)

        exit_code, stdout, stderr = run_cli(
            project_dir,
            "hook-propose",
            "missing-findings.jsonl",
            "--agent",
            "claude",
        )

        assert exit_code == 0
        assert "No fail findings to promote from" in stdout
        assert stderr == ""
        assert not marker_path.exists()
        assert not (project_dir / "packs" / "hook-proposals.json").exists()
