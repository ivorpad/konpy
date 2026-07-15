from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from konpy.cli._hook_findings import HookFinding


def write_claude_stub(
    path: Path,
    *,
    payload: dict[str, object],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        f"print({json.dumps(payload)!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def prepend_stub(
    monkeypatch: pytest.MonkeyPatch,
    stub_bin: Path,
) -> None:
    monkeypatch.setenv(
        "PATH",
        f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )


def seed_findings(path: Path) -> None:
    prompt = "Verify service modules implement their documented behavior."
    findings = [
        HookFinding(
            filePath="src/user_service.py",
            prompt=prompt,
            rule="service-behavior",
            agent="claude",
            model="sonnet",
            reasons=["UserService documents persistence but only validates."],
        ),
        HookFinding(
            filePath="src/order_service.py",
            prompt=prompt,
            rule="service-behavior",
            agent="claude",
            model="sonnet",
            reasons=["OrderService documents persistence but only validates."],
        ),
    ]
    path.write_text(
        "".join(
            f"{finding.model_dump_json(exclude_none=True)}\n"
            for finding in findings
        ),
        encoding="utf-8",
    )


def test_hook_propose_writes_structural_semantic_and_routing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    seed_findings(project_dir / "findings.jsonl")

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        payload={
            "pack": {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "service-files-are-files",
                        "description": "Service modules are regular files.",
                        "paths": "src/**/*_service.py",
                        "must": {"haveType": "file"},
                    }
                ],
            },
            "semantic": [
                {
                    "name": "service-behavior",
                    "prompt": (
                        "Verify service modules implement their documented "
                        "behavior."
                    ),
                    "match": ["src/**/*_service.py"],
                    "source": "Services must implement documented behavior.",
                }
            ],
            "coveredElsewhere": [
                {
                    "rule": "Service functions need return annotations.",
                    "tool": "mypy",
                    "note": "mypy checks declared return types.",
                }
            ],
            "unmapped": [
                {
                    "rule": "Review service metrics weekly.",
                    "reason": "Requires runtime telemetry and process knowledge.",
                }
            ],
        },
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, stderr = run_cli(
        project_dir,
        "hook-propose",
        "findings.jsonl",
        "--agent",
        "claude",
        "--report",
        "reports/routing.md",
    )

    pack_path = project_dir / "packs" / "hook-proposals.json"
    rules_path = project_dir / "packs" / "hook-proposals.rules.json"
    report_path = project_dir / "reports" / "routing.md"

    assert exit_code == 0
    assert "konpy hook-propose: proposing conventions from" in stderr
    assert pack_path.exists()
    assert rules_path.exists()
    assert report_path.exists()

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert pack["conventions"][0]["name"] == "service-files-are-files"
    assert rules["semanticRulesSpecVersion"] == "v1"
    assert rules["rules"][0]["name"] == "service-behavior"
    assert "# Rule routing report" in report
    assert "## Covered by existing linters" in report
    assert "Service functions need return annotations." in report
    assert "mypy checks declared return types." in report
    assert "## Unmapped rules" in report
    assert "Review service metrics weekly." in report
    assert "## Semantic hook wiring" in report
    assert "--rules packs/hook-proposals.rules.json" in report

    assert "Wrote reusable convention proposal to" in stdout
    assert "Wrote semantic rules to packs/hook-proposals.rules.json" in stdout
    assert "Wrote rule-routing report to reports/routing.md" in stdout
    assert "Review service metrics weekly." not in stdout
    assert not (project_dir / "konpy.json").exists()


def test_hook_propose_rules_output_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    seed_findings(project_dir / "findings.jsonl")

    stub_bin = tmp_path / "bin"
    write_claude_stub(
        stub_bin / "claude",
        payload={
            "pack": {
                "conventionSpecVersion": "v1",
                "conventions": [],
            },
            "semantic": [
                {
                    "name": "service-behavior",
                    "prompt": "Verify service behavior.",
                    "match": ["src/**/*_service.py"],
                }
            ],
            "coveredElsewhere": [],
            "unmapped": [],
        },
    )
    prepend_stub(monkeypatch, stub_bin)

    exit_code, stdout, _stderr = run_cli(
        project_dir,
        "hook-propose",
        "findings.jsonl",
        "--agent",
        "claude",
        "--rules-output",
        "generated/service-rules.json",
    )

    assert exit_code == 0
    assert (project_dir / "generated" / "service-rules.json").exists()
    assert not (
        project_dir / "packs" / "hook-proposals.rules.json"
    ).exists()
    assert "generated/service-rules.json" in stdout
