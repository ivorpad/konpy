"""Schema and loader for agent-verifiable semantic rule packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from konpy.config._schema_types import (
    ConventionName,
    NonEmptyString,
    _StrictModel,
)
from konpy.config.errors import Err, Ok, Result, format_validation_error

NonEmptyMatchList = Annotated[list[NonEmptyString], Field(min_length=1)]


class SemanticRuleV1(_StrictModel):
    """One semantic rule verified by a read-only agent against a single file."""

    name: ConventionName
    prompt: NonEmptyString
    match: NonEmptyMatchList
    source: str | None = None


class SemanticRulesPackageV1(_StrictModel):
    """A versioned package consumed by ``konpy hook --rules``."""

    semanticRulesSpecVersion: Literal["v1"]
    rules: list[SemanticRuleV1]


def read_semantic_rules(path: str | Path) -> Result[SemanticRulesPackageV1]:
    """Read and validate a semantic-rules package from disk."""
    source = Path(path)

    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        return Err(f"Could not read semantic rules file: {source}. {error}")

    try:
        decoded: object = json.loads(text)
    except json.JSONDecodeError as error:
        return Err(
            f"Invalid semantic rules file: {source}. "
            f"Malformed JSON at line {error.lineno}, column {error.colno}."
        )

    if not isinstance(decoded, dict):
        return Err(f"Invalid semantic rules file: {source}. Expected a JSON object.")

    try:
        package = SemanticRulesPackageV1.model_validate(decoded)
    except ValidationError as error:
        return Err(
            f"Invalid semantic rules file: {source}:\n"
            f"{format_validation_error(error)}"
        )

    return Ok(package)


__all__ = [
    "SemanticRuleV1",
    "SemanticRulesPackageV1",
    "read_semantic_rules",
]
