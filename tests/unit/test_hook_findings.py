from __future__ import annotations

import json
from pathlib import Path

from konsistent.cli._hook_findings import (
    HookFinding,
    append_hook_finding,
    read_hook_findings,
)
from konsistent.config.errors import Err, Ok


def _finding(
    *,
    file_path: str = "src/example.py",
    prompt: str = "Verify the file.",
    agent: str = "claude",
    model: str = "sonnet",
    reasons: list[str] | None = None,
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        agent=agent,
        model=model,
        reasons=["verification failed"] if reasons is None else reasons,
    )


def test_hook_finding_round_trips_through_json() -> None:
    finding = _finding(
        file_path="src/service.py",
        prompt="Verify the implementation matches its docstring.",
        reasons=["docstring does not match method body"],
    )

    encoded = finding.model_dump_json()
    decoded = json.loads(encoded)
    round_tripped = HookFinding.model_validate(decoded)

    assert decoded["schemaVersion"] == "v1"
    assert decoded["verdict"] == "fail"
    assert round_tripped == finding


def test_append_hook_finding_creates_parents_and_appends_one_line_per_call(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "hook" / "findings.jsonl"

    first_result = append_hook_finding(
        log_path,
        _finding(file_path="src/first.py", reasons=["first reason"]),
    )
    second_result = append_hook_finding(
        log_path,
        _finding(file_path="src/second.py", reasons=["second reason"]),
    )

    assert isinstance(first_result, Ok)
    assert isinstance(second_result, Ok)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    records = [json.loads(line) for line in lines]
    assert records[0]["filePath"] == "src/first.py"
    assert records[0]["reasons"] == ["first reason"]
    assert records[1]["filePath"] == "src/second.py"
    assert records[1]["reasons"] == ["second reason"]


def test_append_hook_finding_returns_err_when_parent_is_existing_file(
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")

    result = append_hook_finding(blocker / "findings.jsonl", _finding())

    assert isinstance(result, Err)
    assert "Could not append hook finding log:" in result.error


def test_read_hook_findings_missing_file_returns_empty_without_warnings(
    tmp_path: Path,
) -> None:
    findings, warnings = read_hook_findings(tmp_path / "missing.jsonl")

    assert findings == []
    assert warnings == []


def test_read_hook_findings_skips_invalid_lines_with_ordered_warnings(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "findings.jsonl"
    valid_one = _finding(file_path="src/valid_one.py", reasons=["first valid"])
    valid_two = _finding(file_path="src/valid_two.py", reasons=["second valid"])
    non_fail = {
        "schemaVersion": "v1",
        "verdict": "pass",
        "filePath": "src/pass.py",
        "prompt": "Verify it.",
        "agent": "claude",
        "model": "sonnet",
        "reasons": [],
    }
    schema_invalid = {
        "schemaVersion": "v1",
        "verdict": "fail",
        "filePath": "src/invalid.py",
        "prompt": "Verify it.",
        "agent": "claude",
        "model": "sonnet",
        "reasons": [],
    }

    log_path.write_text(
        "\n".join(
            [
                valid_one.model_dump_json(exclude_none=True),
                "",
                "{not json",
                json.dumps(["not", "an", "object"]),
                json.dumps(non_fail),
                json.dumps(schema_invalid),
                valid_two.model_dump_json(exclude_none=True),
                "   ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings, warnings = read_hook_findings(log_path)

    assert [finding.filePath for finding in findings] == [
        "src/valid_one.py",
        "src/valid_two.py",
    ]
    assert len(warnings) == 4
    assert f"{log_path}:3" in warnings[0]
    assert "malformed JSON" in warnings[0]
    assert f"{log_path}:4" in warnings[1]
    assert "expected object" in warnings[1]
    assert f"{log_path}:5" in warnings[2]
    assert "non-fail" in warnings[2]
    assert f"{log_path}:6" in warnings[3]
    assert "reasons" in warnings[3]
