"""Persisted JSONL findings for verified `konsistent hook` fail verdicts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from konsistent.config.errors import Err, Ok, Result, format_validation_error

DEFAULT_FINDINGS_LOG_PATH = ".konsistent/hook-findings.jsonl"


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


class HookFinding(BaseModel):
    """A persisted verified fail verdict from `konsistent hook`."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schemaVersion: Literal["v1"] = "v1"
    verdict: Literal["fail"] = "fail"
    loggedAt: str = Field(default_factory=_utc_timestamp)
    sessionId: str | None = None
    cwd: str | None = None
    toolName: str | None = None
    filePath: str
    prompt: str
    agent: str
    model: str
    reasons: list[str] = Field(min_length=1)


def append_hook_finding(path: str | Path, finding: HookFinding) -> Result[None]:
    """Append one hook finding as JSONL, creating parent directories when needed."""
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(finding.model_dump_json(exclude_none=True))
            handle.write("\n")
    except OSError as error:
        return Err(f"Could not append hook finding log: {destination}. {error}")

    return Ok(None)


def read_hook_findings(path: str | Path) -> tuple[list[HookFinding], list[str]]:
    """Read valid fail findings from a JSONL log, returning ordered skip warnings."""
    source = Path(path)
    if not source.exists():
        return ([], [])

    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return ([], [f"Could not read hook findings log: {source}. {error}"])

    findings: list[HookFinding] = []
    warnings: list[str] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        location = f"{source}:{line_number}"

        try:
            decoded: object = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"Skipping invalid hook finding at {location}: malformed JSON.")
            continue

        if not isinstance(decoded, dict):
            warnings.append(f"Skipping invalid hook finding at {location}: expected object.")
            continue

        verdict = decoded.get("verdict")
        if verdict is None:
            warnings.append(f"Skipping invalid hook finding at {location}: missing fail verdict.")
            continue
        if verdict != "fail":
            warnings.append(f"Skipping non-fail hook finding at {location}.")
            continue

        try:
            findings.append(HookFinding.model_validate(decoded))
        except ValidationError as error:
            warnings.append(
                f"Skipping invalid hook finding at {location}:\n"
                f"{format_validation_error(error)}"
            )

    return (findings, warnings)


__all__ = [
    "DEFAULT_FINDINGS_LOG_PATH",
    "HookFinding",
    "append_hook_finding",
    "read_hook_findings",
]
