"""Semantic-rules prompt, verdict parsing, and normalization."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict

from konpy.cli._semantic_rules import SemanticRuleV1
from konpy.cli.agent_runner import first_json_object
from konpy.config.errors import Err, Ok, Result


class RuleFailure(TypedDict):
    """One failed semantic rule returned by a batched verifier."""

    rule: str
    reasons: list[str]


class RulesVerdict(TypedDict):
    """Normalized batched semantic-rules verdict."""

    verdict: Literal["pass", "fail"]
    failures: list[RuleFailure]


class NormalizedRuleFailure(TypedDict):
    """A failed rule joined back to its package definition."""

    rule: SemanticRuleV1
    reasons: list[str]


def build_rules_hook_prompt(
    *,
    file_path: str,
    cwd: str,
    rules: Sequence[SemanticRuleV1],
) -> str:
    """Build one batched verifier prompt for all applicable rules on a file."""
    rules_text = "\n\n".join(
        f'Rule "{rule.name}":\n{rule.prompt}' for rule in rules
    )
    return f"""\
You are a read-only verification agent invoked from a konpy PostToolUse hook.

Working directory: {cwd}
File to inspect (read-only; do not modify): {file_path}

Verify every rule listed below against this one file.

{rules_text}

Read the file yourself using your available read-only tools. If the file is
unreadable or missing, return a pass. If one rule does not apply after
inspection, treat that rule as passing. Do not modify any file.

Return exactly one JSON object with one of these contracts and nothing else:

{{"verdict": "pass", "failures": []}}

{{"verdict": "fail", "failures": [
  {{"rule": "listed-rule-name", "reasons": ["Concrete feedback."]}}
]}}

Only rule names listed above are valid. A pass requires an empty "failures"
list. Include one entry for each violated rule. Each reason is shown directly
to the coding agent that wrote the file, so make it concrete and actionable.
"""


def parse_rules_verdict(stdout: str) -> RulesVerdict | None:
    """Parse a batched semantic-rules verifier verdict."""
    candidate = first_json_object(
        stdout,
        predicate=lambda obj: obj.get("verdict") in {"pass", "fail"},
    )
    if candidate is None:
        return None

    verdict = candidate.get("verdict")
    if verdict not in {"pass", "fail"}:
        return None

    raw_failures = candidate.get("failures", [])
    if raw_failures is None:
        raw_failures = []
    if not isinstance(raw_failures, list):
        return None

    failures: list[RuleFailure] = []
    for raw_failure in raw_failures:
        if not isinstance(raw_failure, dict):
            return None
        rule = raw_failure.get("rule")
        if not isinstance(rule, str):
            return None

        reasons = raw_failure.get("reasons", [])
        if reasons is None:
            reasons = []
        if not isinstance(reasons, list):
            return None
        failures.append(
            {
                "rule": rule,
                "reasons": [str(reason) for reason in reasons],
            }
        )

    return {"verdict": verdict, "failures": failures}


def normalize_rules_verdict(
    verdict: RulesVerdict,
    *,
    applicable_rules: Sequence[SemanticRuleV1],
    file_path: str,
) -> Result[list[NormalizedRuleFailure]]:
    """Validate and order failures against the applicable package rules."""
    if verdict["verdict"] == "pass":
        if verdict["failures"]:
            return Err('A "pass" rules verdict must have no failures.')
        return Ok([])

    by_name: dict[str, list[str]] = {}
    applicable_by_name = {rule.name: rule for rule in applicable_rules}
    for failure in verdict["failures"]:
        name = failure["rule"]
        if name not in applicable_by_name:
            return Err(
                f'Rules verdict named unknown or inapplicable rule "{name}".'
            )
        reasons = by_name.setdefault(name, [])
        for reason in failure["reasons"]:
            if reason not in reasons:
                reasons.append(reason)

    generic = (
        f"Verification failed for {file_path} without a rule-specific reason."
    )
    if not by_name:
        by_name[applicable_rules[0].name] = [generic]

    normalized: list[NormalizedRuleFailure] = []
    emitted: set[str] = set()
    for rule in applicable_rules:
        if rule.name in emitted or rule.name not in by_name:
            continue
        emitted.add(rule.name)
        normalized.append(
            {
                "rule": rule,
                "reasons": by_name[rule.name] or [generic],
            }
        )
    return Ok(normalized)


__all__ = [
    "NormalizedRuleFailure",
    "RuleFailure",
    "RulesVerdict",
    "build_rules_hook_prompt",
    "normalize_rules_verdict",
    "parse_rules_verdict",
]
