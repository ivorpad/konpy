from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from konpy.cli._extract_rules_prompt import build_prompt, read_predicates_reference
from konpy.cli.agent_runner import (
    _FENCE_RE,
    AGENT_COMMANDS,
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    ExtractAgent,
    _test_invocation_for_runner,
    first_json_object,
    iter_json_objects,
    run_agent_subprocess,
    select_agent_invocation,
)
from konpy.cli.agent_runner import _normalize_agent as _normalize_agent_value
from konpy.config.errors import Err, Ok, Result, format_validation_error
from konpy.config.schema import ReusableConventionsPackageV1


def run_extract_rules_command(
    *,
    source_file: str,
    output_path: str | None,
    agent: ExtractAgent | str,
    report_path: str | None,
    model: str = DEFAULT_MODEL,
    runner: AgentRunner | None = None,
) -> int:
    """Run the `konpy extract-rules` flow end to end.

    Reads `source_file`, invokes an agent CLI to convert its prose rules into
    a `ReusableConventionsPackageV1`-shaped proposal plus an unmapped-rules
    report, validates the result, and writes the proposal (and optionally the
    report) to disk.
    """
    agent_value_result = _normalize_agent_value(agent)
    if isinstance(agent_value_result, Err):
        _write_error(agent_value_result.error)
        return 1
    agent_value = agent_value_result.value

    source_path = Path(source_file)
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as error:
        _write_error(f"Could not read source file: {source_path}. {error}")
        return 1

    predicates_reference_result = read_predicates_reference()
    if isinstance(predicates_reference_result, Err):
        _write_error(predicates_reference_result.error)
        return 1

    invocation_result: Result[AgentInvocation]
    if runner is None:
        invocation_result = select_agent_invocation(agent_value)
    else:
        invocation_result = _test_invocation_for_runner(agent_value)

    if isinstance(invocation_result, Err):
        _write_error(invocation_result.error)
        return 1
    invocation = invocation_result.value

    prompt = build_prompt(
        source_text=source_text,
        source_label=str(source_path),
        predicates_reference=predicates_reference_result.value,
    )

    run_result = _run_agent(invocation=invocation, prompt=prompt, runner=runner, model=model)
    if run_result.returncode != 0:
        _write_error(
            f'Agent CLI "{invocation.agent}" exited with code {run_result.returncode}.'
        )
        if run_result.stderr.strip():
            _write_error(run_result.stderr.strip())
        elif run_result.stdout.strip():
            _write_error(run_result.stdout.strip())
        return 1

    parsed_result = extract_agent_json_object(run_result.stdout)
    if isinstance(parsed_result, Err):
        _write_error(parsed_result.error)
        return 1

    contract_result = validate_agent_response_contract(parsed_result.value)
    if isinstance(contract_result, Err):
        _write_error(contract_result.error)
        return 1
    pack_value, unmapped = contract_result.value

    try:
        pack = ReusableConventionsPackageV1.model_validate(pack_value)
    except ValidationError as error:
        _write_error(
            "Invalid extracted reusable-convention package:\n"
            f"{format_validation_error(error)}"
        )
        return 1

    destination = _default_output_path(source_file) if output_path is None else Path(output_path)
    report_destination = Path(report_path) if report_path is not None else None

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                pack.model_dump(by_alias=True, exclude_none=True, mode="json"),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        _write_error(f"Could not write extracted reusable convention pack: {destination}. {error}")
        return 1

    if report_destination is not None:
        try:
            report_destination.parent.mkdir(parents=True, exist_ok=True)
            report_destination.write_text(format_unmapped_report(unmapped), encoding="utf-8")
        except OSError as error:
            _write_error(f"Could not write unmapped-rules report: {report_destination}. {error}")
            return 1

    sys.stdout.write(f"Wrote reusable convention proposal to {destination}\n")
    if report_destination is None:
        sys.stdout.write(format_unmapped_stdout(unmapped))
    else:
        sys.stdout.write(f"Wrote unmapped-rules report to {report_destination}\n")

    return 0


def extract_agent_json_object(response_text: str) -> Result[dict[str, object]]:
    """Extract the agent's JSON object response from fenced or bare text."""
    candidates: list[dict[str, object]] = []

    for match in _FENCE_RE.finditer(response_text.strip()):
        candidates.extend(iter_json_objects(match.group("body")))

    candidates.extend(iter_json_objects(response_text))

    for candidate in candidates:
        if "pack" in candidate and "unmapped" in candidate:
            return Ok(candidate)

    if candidates:
        return Ok(candidates[0])

    return Err("Agent response did not contain a valid JSON object.")


def validate_agent_response_contract(
    value: dict[str, object],
) -> Result[tuple[object, list[dict[str, str]]]]:
    """Validate the agent JSON object has the required `pack`/`unmapped` shape."""
    if "pack" not in value or "unmapped" not in value:
        return Err('Invalid agent response: expected keys "pack" and "unmapped".')

    unmapped = value["unmapped"]
    if not isinstance(unmapped, list):
        return Err(
            'Invalid agent response: "unmapped" must be a list of objects with '
            'string "rule" and "reason" fields.'
        )

    normalized: list[dict[str, str]] = []
    for item in unmapped:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("rule"), str)
            or not isinstance(item.get("reason"), str)
        ):
            return Err(
                'Invalid agent response: "unmapped" must be a list of objects with '
                'string "rule" and "reason" fields.'
            )
        normalized.append({"rule": item["rule"], "reason": item["reason"]})

    return Ok((value["pack"], normalized))


def format_unmapped_stdout(unmapped: list[dict[str, str]]) -> str:
    """Format unmapped rules for stdout after writing an extracted pack."""
    if not unmapped:
        return "Unmapped rules: none\n"

    lines = ["Unmapped rules:"]
    lines.extend(f"- {item['rule']}: {item['reason']}" for item in unmapped)
    return "\n".join(lines) + "\n"


def format_unmapped_report(unmapped: list[dict[str, str]]) -> str:
    """Format unmapped rules as a Markdown report."""
    if not unmapped:
        return "# Unmapped rules\n\nNone.\n"

    lines = ["# Unmapped rules", ""]
    lines.extend(f"- **{item['rule']}**: {item['reason']}" for item in unmapped)
    return "\n".join(lines) + "\n"


def _run_agent(
    *,
    invocation: AgentInvocation,
    prompt: str,
    runner: AgentRunner | None,
    model: str,
) -> AgentRunResult:
    if runner is not None:
        result = runner(invocation, prompt)
        if isinstance(result, AgentRunResult):
            return result
        return AgentRunResult(returncode=0, stdout=result, stderr="")

    return run_agent_subprocess(invocation=invocation, prompt=prompt, model=model)


def _default_output_path(source_file: str) -> Path:
    return Path.cwd() / "packs" / f"{Path(source_file).stem}.json"


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = [
    "AGENT_COMMANDS",
    "DEFAULT_MODEL",
    "AgentInvocation",
    "AgentRunResult",
    "AgentRunner",
    "ExtractAgent",
    "build_prompt",
    "extract_agent_json_object",
    "first_json_object",
    "format_unmapped_report",
    "format_unmapped_stdout",
    "iter_json_objects",
    "read_predicates_reference",
    "run_agent_subprocess",
    "run_extract_rules_command",
    "select_agent_invocation",
    "validate_agent_response_contract",
]
