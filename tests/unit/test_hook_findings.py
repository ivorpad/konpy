from __future__ import annotations

import json
from pathlib import Path

from konpy.cli._hook_findings import (
    HookFinding,
    append_hook_finding,
    read_hook_findings,
)
from konpy.config.errors import Err, Ok


def finding(
    *,
    file_path: str = "src/example.py",
    prompt: str = "Verify the file.",
    rule: str | None = None,
    reasons: list[str] | None = None,
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        rule=rule,
        agent="claude",
        model="sonnet",
        reasons=["verification failed"] if reasons is None else reasons,
    )


def test_old_finding_without_rule_remains_valid() -> None:
    record = {
        "schemaVersion": "v1",
        "verdict": "fail",
        "filePath": "src/old.py",
        "prompt": "Verify the old rule.",
        "agent": "claude",
        "model": "sonnet",
        "reasons": ["old failure"],
    }

    parsed = HookFinding.model_validate(record)

    assert parsed.rule is None
    assert "rule" not in parsed.model_dump(exclude_none=True)


def test_new_finding_with_rule_round_trips() -> None:
    original = finding(
        file_path="src/service.py",
        prompt="Verify service behavior.",
        rule="service-behavior",
        reasons=["service does not perform the documented operation"],
    )

    encoded = original.model_dump_json(exclude_none=True)
    parsed = HookFinding.model_validate_json(encoded)

    assert parsed == original
    assert json.loads(encoded)["rule"] == "service-behavior"


def test_extra_fields_remain_ignored_for_compatibility() -> None:
    parsed = HookFinding.model_validate(
        {
            "schemaVersion": "v1",
            "verdict": "fail",
            "filePath": "src/x.py",
            "prompt": "Verify it.",
            "rule": "known-rule",
            "agent": "claude",
            "model": "sonnet",
            "reasons": ["failed"],
            "futureField": {"value": True},
        }
    )

    assert parsed.rule == "known-rule"
    assert not hasattr(parsed, "futureField")


def test_append_and_read_round_trip_old_and_new_records(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "findings.jsonl"

    old_result = append_hook_finding(
        log_path,
        finding(file_path="src/old.py"),
    )
    new_result = append_hook_finding(
        log_path,
        finding(
            file_path="src/new.py",
            rule="new-rule",
            prompt="Verify the new rule.",
        ),
    )

    findings, warnings = read_hook_findings(log_path)

    assert isinstance(old_result, Ok)
    assert isinstance(new_result, Ok)
    assert warnings == []
    assert [item.filePath for item in findings] == [
        "src/old.py",
        "src/new.py",
    ]
    assert [item.rule for item in findings] == [None, "new-rule"]


def test_append_creates_parent_and_one_json_object_per_line(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "nested" / "findings.jsonl"

    append_hook_finding(
        log_path,
        finding(file_path="src/a.py", reasons=["a"]),
    )
    append_hook_finding(
        log_path,
        finding(
            file_path="src/b.py",
            rule="rule-b",
            reasons=["b"],
        ),
    )

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 2
    assert records[0]["filePath"] == "src/a.py"
    assert "rule" not in records[0]
    assert records[1]["filePath"] == "src/b.py"
    assert records[1]["rule"] == "rule-b"


def test_append_returns_err_for_unwritable_destination(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    result = append_hook_finding(
        blocker / "findings.jsonl",
        finding(),
    )

    assert isinstance(result, Err)
    assert "Could not append hook finding log:" in result.error


def test_missing_log_returns_empty_without_warnings(tmp_path: Path) -> None:
    findings, warnings = read_hook_findings(tmp_path / "missing.jsonl")

    assert findings == []
    assert warnings == []


def test_reader_skips_invalid_and_non_fail_lines_with_warnings(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "findings.jsonl"
    valid = finding(
        file_path="src/valid.py",
        rule="valid-rule",
    )
    invalid_schema = {
        "schemaVersion": "v1",
        "verdict": "fail",
        "filePath": "src/invalid.py",
        "prompt": "Verify it.",
        "agent": "claude",
        "model": "sonnet",
        "reasons": [],
    }
    non_fail = {
        "schemaVersion": "v1",
        "verdict": "pass",
        "filePath": "src/pass.py",
        "prompt": "Verify it.",
        "agent": "claude",
        "model": "sonnet",
        "reasons": [],
    }
    log_path.write_text(
        "\n".join(
            [
                "{not json",
                json.dumps(["not", "an", "object"]),
                json.dumps(non_fail),
                json.dumps(invalid_schema),
                valid.model_dump_json(exclude_none=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings, warnings = read_hook_findings(log_path)

    assert [item.filePath for item in findings] == ["src/valid.py"]
    assert findings[0].rule == "valid-rule"
    assert len(warnings) == 4
    assert "malformed JSON" in warnings[0]
    assert "expected object" in warnings[1]
    assert "non-fail" in warnings[2]
    assert "reasons" in warnings[3]
