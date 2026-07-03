"""Implementation of `konsistent hook-propose`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

from konsistent.cli._extract_rules_prompt import read_predicates_reference
from konsistent.cli._hook_findings import read_hook_findings
from konsistent.cli._propose_prompt import build_propose_prompt
from konsistent.cli._propose_support import aggregate_findings
from konsistent.cli.agent_runner import (
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    ExtractAgent,
    _test_invocation_for_runner,
    run_agent_subprocess,
    select_agent_invocation,
)
from konsistent.cli.agent_runner import _normalize_agent as _normalize_agent_value
from konsistent.cli.extract_rules import (
    extract_agent_json_object,
    format_unmapped_report,
    format_unmapped_stdout,
    validate_agent_response_contract,
)
from konsistent.config.errors import Err, Result, format_validation_error
from konsistent.config.schema import ReusableConventionsPackageV1


def run_propose_command(
    *,
    findings_path: str,
    output_path: str | None,
    agent: ExtractAgent | str,
    report_path: str | None,
    model: str = DEFAULT_MODEL,
    timeout: float | None = None,
    runner: AgentRunner | None = None,
) -> int:
    """Run the `konsistent hook-propose` flow end to end."""
    findings, warnings = read_hook_findings(findings_path)
    for warning in warnings:
        _write_error(warning)

    if not findings:
        sys.stdout.write(f"No fail findings to promote from {findings_path}.\n")
        return 0

    aggregated = aggregate_findings(findings)

    predicates_reference_result = read_predicates_reference()
    if isinstance(predicates_reference_result, Err):
        _write_error(predicates_reference_result.error)
        return 1

    agent_value_result = _normalize_agent_value(agent)
    if isinstance(agent_value_result, Err):
        _write_error(agent_value_result.error)
        return 1
    agent_value = agent_value_result.value

    invocation_result: Result[AgentInvocation]
    if runner is None:
        invocation_result = select_agent_invocation(agent_value)
    else:
        invocation_result = _test_invocation_for_runner(agent_value)

    if isinstance(invocation_result, Err):
        _write_error(invocation_result.error)
        return 1
    invocation = invocation_result.value

    prompt = build_propose_prompt(
        aggregated=aggregated,
        predicates_reference=predicates_reference_result.value,
    )

    run_result = _run_agent(
        invocation=invocation,
        prompt=prompt,
        runner=runner,
        model=model,
        timeout=timeout,
    )
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
            "Invalid proposed reusable-convention package:\n"
            f"{format_validation_error(error)}"
        )
        return 1

    destination = _default_output_path() if output_path is None else Path(output_path)
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
        _write_error(f"Could not write reusable convention proposal: {destination}. {error}")
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


def _run_agent(
    *,
    invocation: AgentInvocation,
    prompt: str,
    runner: AgentRunner | None,
    model: str,
    timeout: float | None,
) -> AgentRunResult:
    if runner is not None:
        result = runner(invocation, prompt)
        if isinstance(result, AgentRunResult):
            return result
        return AgentRunResult(returncode=0, stdout=result, stderr="")

    return run_agent_subprocess(
        invocation=invocation,
        prompt=prompt,
        model=model,
        timeout=timeout,
    )


def _default_output_path() -> Path:
    return Path.cwd() / "packs" / "hook-proposals.json"


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["run_propose_command"]
