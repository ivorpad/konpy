"""Validation and normalization for extract-rules agent responses."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from pydantic import ValidationError

from konpy.cli._semantic_rules import (
    SemanticRulesPackageV1,
    SemanticRuleV1,
)
from konpy.config.errors import Err, Ok, Result, format_validation_error


class CoveredElsewhereEntry(TypedDict):
    """A source rule already enforced by Ruff, a type checker, or Import Linter."""

    rule: str
    tool: str
    note: NotRequired[str]


class UnmappedEntry(TypedDict):
    """A source rule that cannot be handled by the available lanes."""

    rule: str
    reason: str


type AgentResponseContract = tuple[
    object,
    list[SemanticRuleV1],
    list[CoveredElsewhereEntry],
    list[UnmappedEntry],
]


def validate_agent_response_contract(
    value: dict[str, object],
) -> Result[AgentResponseContract]:
    """Validate and normalize all four extraction lanes."""
    if "pack" not in value or "unmapped" not in value:
        return Err('Invalid agent response: expected keys "pack" and "unmapped".')

    semantic_result = _validate_semantic(value.get("semantic", []))
    if isinstance(semantic_result, Err):
        return semantic_result

    covered_result = _validate_covered_elsewhere(
        value.get("coveredElsewhere", [])
    )
    if isinstance(covered_result, Err):
        return covered_result

    unmapped_result = _validate_unmapped(value["unmapped"])
    if isinstance(unmapped_result, Err):
        return unmapped_result

    return Ok(
        (
            value["pack"],
            semantic_result.value,
            covered_result.value,
            unmapped_result.value,
        )
    )


def _validate_semantic(value: object) -> Result[list[SemanticRuleV1]]:
    if not isinstance(value, list):
        return Err(
            'Invalid agent response: "semantic" must be a list of semantic '
            "rule objects."
        )

    try:
        package = SemanticRulesPackageV1.model_validate(
            {
                "semanticRulesSpecVersion": "v1",
                "rules": value,
            }
        )
    except ValidationError as error:
        return Err(
            'Invalid agent response: "semantic" entries are invalid:\n'
            f"{format_validation_error(error)}"
        )

    return Ok(package.rules)


def _validate_covered_elsewhere(
    value: object,
) -> Result[list[CoveredElsewhereEntry]]:
    error_message = (
        'Invalid agent response: "coveredElsewhere" must be a list of objects '
        'with string "rule" and "tool" fields and an optional string "note".'
    )
    if not isinstance(value, list):
        return Err(error_message)

    normalized: list[CoveredElsewhereEntry] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("rule"), str)
            or not isinstance(item.get("tool"), str)
        ):
            return Err(error_message)

        note = item.get("note")
        if "note" in item and not isinstance(note, str):
            return Err(error_message)

        entry: CoveredElsewhereEntry = {
            "rule": item["rule"],
            "tool": item["tool"],
        }
        if isinstance(note, str):
            entry["note"] = note
        normalized.append(entry)

    return Ok(normalized)


def _validate_unmapped(value: object) -> Result[list[UnmappedEntry]]:
    error_message = (
        'Invalid agent response: "unmapped" must be a list of objects with '
        'string "rule" and "reason" fields.'
    )
    if not isinstance(value, list):
        return Err(error_message)

    normalized: list[UnmappedEntry] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("rule"), str)
            or not isinstance(item.get("reason"), str)
        ):
            return Err(error_message)

        normalized.append(
            {
                "rule": item["rule"],
                "reason": item["reason"],
            }
        )

    return Ok(normalized)


__all__ = [
    "AgentResponseContract",
    "CoveredElsewhereEntry",
    "UnmappedEntry",
    "validate_agent_response_contract",
]
