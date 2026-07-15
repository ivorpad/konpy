"""Implementation of `konpy hook-propose`."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

from konpy.cli._agent_stream import AgentProgressReporter
from konpy.cli._extract_rules_prompt import read_predicates_reference
from konpy.cli._hook_findings import read_hook_findings
from konpy.cli._propose_prompt import build_propose_prompt
from konpy.cli._propose_support import aggregate_findings
from konpy.cli._rule_artifacts import (
    derive_rules_output_path,
    validate_artifact_destinations,
    write_model_artifact,
    write_text_artifact,
)
from konpy.cli._semantic_rules import SemanticRulesPackageV1
from konpy.cli.agent_runner import (
    DEFAULT_MODEL,
    AgentInvocation,
    AgentRunner,
    AgentRunResult,
    ExtractAgent,
    _test_invocation_for_runner,
    run_agent_subprocess,
    select_agent_invocation,
)
from konpy.cli.agent_runner import _normalize_agent as _normalize_agent_value
from konpy.cli.extract_rules import (
    extract_agent_json_object,
    format_unmapped_report,
    format_unmapped_stdout,
    validate_agent_response_contract,
)
from konpy.config.errors import Err, Result, format_validation_error
from konpy.config.schema import ReusableConventionsPackageV1


def run_propose_command(
    *,
    findings_path: str,
    output_path: str | None,
    agent: ExtractAgent | str,
    report_path: str | None,
    model: str = DEFAULT_MODEL,
    timeout: float | None = None,
    verbose: bool = False,
    runner: AgentRunner | None = None,
    rules_output_path: str | None = None,
) -> int:
    """Promote hook findings into structural and semantic rule proposals."""
    findings, warnings = read_hook_findings(findings_path)
    for warning in warnings:
        _write_error(warning)

    if not findings:
        sys.stdout.write(
            f"No fail findings to promote from {findings_path}.\n"
        )
        return 0

    aggregated = aggregate_findings(findings)
    predicates_result = read_predicates_reference()
    if isinstance(predicates_result, Err):
        _write_error(predicates_result.error)
        return 1

    agent_result = _normalize_agent_value(agent)
    if isinstance(agent_result, Err):
        _write_error(agent_result.error)
        return 1
    agent_value = agent_result.value

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
        predicates_reference=predicates_result.value,
    )
    reporter = _start_reporter(
        invocation=invocation,
        group_count=len(aggregated),
        prompt=prompt,
        model=model,
        verbose=verbose,
        enabled=runner is None,
    )
    run_result = _run_agent(
        invocation=invocation,
        prompt=prompt,
        runner=runner,
        model=model,
        timeout=timeout,
        reporter=reporter,
    )
    if reporter is not None:
        reporter.finish()

    if run_result.returncode != 0:
        _write_agent_failure(invocation, run_result)
        return 1

    response_text = (
        run_result.stdout
        if reporter is None
        else reporter.finalize_stdout(run_result.stdout)
    )
    parsed_result = extract_agent_json_object(response_text)
    if isinstance(parsed_result, Err):
        _write_error(parsed_result.error)
        return 1

    contract_result = validate_agent_response_contract(parsed_result.value)
    if isinstance(contract_result, Err):
        _write_error(contract_result.error)
        return 1
    pack_value, semantic, covered_elsewhere, unmapped = contract_result.value

    try:
        pack = ReusableConventionsPackageV1.model_validate(pack_value)
    except ValidationError as error:
        _write_error(
            "Invalid proposed reusable-convention package:\n"
            f"{format_validation_error(error)}"
        )
        return 1

    semantic_package = SemanticRulesPackageV1(
        semanticRulesSpecVersion="v1",
        rules=semantic,
    )
    destination = (
        _default_output_path() if output_path is None else Path(output_path)
    )
    rules_destination = _rules_destination(
        destination=destination,
        rules_output_path=rules_output_path,
        has_rules=bool(semantic),
    )
    report_destination = Path(report_path) if report_path is not None else None

    collision_result = validate_artifact_destinations(
        pack_path=destination,
        rules_path=rules_destination,
        report_path=report_destination,
    )
    if isinstance(collision_result, Err):
        _write_error(collision_result.error)
        return 1

    write_result = write_model_artifact(
        destination,
        pack,
        artifact_label="reusable convention proposal",
    )
    if isinstance(write_result, Err):
        _write_error(write_result.error)
        return 1

    if rules_destination is not None:
        write_result = write_model_artifact(
            rules_destination,
            semantic_package,
            artifact_label="semantic rules",
        )
        if isinstance(write_result, Err):
            _write_error(write_result.error)
            return 1

    if report_destination is not None:
        write_result = write_text_artifact(
            report_destination,
            format_unmapped_report(
                unmapped,
                covered_elsewhere=covered_elsewhere,
                rules_path=rules_destination,
            ),
            artifact_label="rule-routing report",
        )
        if isinstance(write_result, Err):
            _write_error(write_result.error)
            return 1

    sys.stdout.write(f"Wrote reusable convention proposal to {destination}\n")
    if rules_destination is not None:
        sys.stdout.write(f"Wrote semantic rules to {rules_destination}\n")
    if report_destination is None:
        sys.stdout.write(
            format_unmapped_stdout(
                unmapped,
                covered_elsewhere=covered_elsewhere,
                rules_path=rules_destination,
            )
        )
    else:
        sys.stdout.write(
            f"Wrote rule-routing report to {report_destination}\n"
        )
    return 0


def _start_reporter(
    *,
    invocation: AgentInvocation,
    group_count: int,
    prompt: str,
    model: str,
    verbose: bool,
    enabled: bool,
) -> AgentProgressReporter | None:
    if not enabled:
        return None
    reporter = AgentProgressReporter(
        command="hook-propose",
        invocation=invocation,
        model=model,
        verbose=verbose,
    )
    reporter.announce(
        f"proposing conventions from {group_count} finding group(s) "
        f"(prompt {len(prompt)} chars)"
    )
    return reporter


def _run_agent(
    *,
    invocation: AgentInvocation,
    prompt: str,
    runner: AgentRunner | None,
    model: str,
    timeout: float | None,
    reporter: AgentProgressReporter | None,
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
        extra_args=() if reporter is None else reporter.extra_args,
        on_progress=None if reporter is None else reporter.on_progress,
        on_output_line=None if reporter is None else reporter.output_line_callback,
    )


def _write_agent_failure(
    invocation: AgentInvocation,
    run_result: AgentRunResult,
) -> None:
    _write_error(
        f'Agent CLI "{invocation.agent}" exited with code {run_result.returncode}.'
    )
    if run_result.stderr.strip():
        _write_error(run_result.stderr.strip())
    elif run_result.stdout.strip():
        _write_error(run_result.stdout.strip())


def _rules_destination(
    *,
    destination: Path,
    rules_output_path: str | None,
    has_rules: bool,
) -> Path | None:
    if not has_rules:
        return None
    if rules_output_path is not None:
        return Path(rules_output_path)
    return derive_rules_output_path(destination)


def _default_output_path() -> Path:
    return Path("packs") / "hook-proposals.json"


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["run_propose_command"]
