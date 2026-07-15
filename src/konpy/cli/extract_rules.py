from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

from konpy.cli._agent_stream import AgentProgressReporter
from konpy.cli._extract_rules_contract import validate_agent_response_contract
from konpy.cli._extract_rules_output import write_extraction_artifacts
from konpy.cli._extract_rules_prompt import build_prompt, read_predicates_reference
from konpy.cli._extract_rules_report import (
    format_unmapped_report,
    format_unmapped_stdout,
)
from konpy.cli._semantic_rules import SemanticRulesPackageV1
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
    timeout: float | None = None,
    verbose: bool = False,
    runner: AgentRunner | None = None,
    rules_output_path: str | None = None,
) -> int:
    """Extract structural and semantic rules from a prose source."""
    agent_result = _normalize_agent_value(agent)
    if isinstance(agent_result, Err):
        _write_error(agent_result.error)
        return 1
    agent_value = agent_result.value

    source_path = Path(source_file)
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as error:
        _write_error(f"Could not read source file: {source_path}. {error}")
        return 1

    predicates_result = read_predicates_reference()
    if isinstance(predicates_result, Err):
        _write_error(predicates_result.error)
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
        predicates_reference=predicates_result.value,
    )
    reporter = _start_reporter(
        invocation=invocation,
        source_path=source_path,
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
            "Invalid extracted reusable-convention package:\n"
            f"{format_validation_error(error)}"
        )
        return 1

    semantic_package = SemanticRulesPackageV1(
        semanticRulesSpecVersion="v1",
        rules=semantic,
    )
    destination = (
        _default_output_path(source_file)
        if output_path is None
        else Path(output_path)
    )
    artifacts_result = write_extraction_artifacts(
        pack=pack,
        semantic_package=semantic_package,
        destination=destination,
        rules_output_path=rules_output_path,
        report_path=report_path,
        covered_elsewhere=covered_elsewhere,
        unmapped=unmapped,
    )
    if isinstance(artifacts_result, Err):
        _write_error(artifacts_result.error)
        return 1

    destination, rules_destination, report_destination = artifacts_result.value
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
        sys.stdout.write(f"Wrote rule-routing report to {report_destination}\n")
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


def _start_reporter(
    *,
    invocation: AgentInvocation,
    source_path: Path,
    prompt: str,
    model: str,
    verbose: bool,
    enabled: bool,
) -> AgentProgressReporter | None:
    if not enabled:
        return None
    reporter = AgentProgressReporter(
        command="extract-rules",
        invocation=invocation,
        model=model,
        verbose=verbose,
    )
    reporter.announce(
        f"extracting from {source_path} (prompt {len(prompt)} chars)"
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


def _default_output_path(source_file: str) -> Path:
    return Path("packs") / f"{Path(source_file).stem}.json"


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
