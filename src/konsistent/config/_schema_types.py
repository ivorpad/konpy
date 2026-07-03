from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CONVENTION_NAME_PATTERN = r"^[a-z0-9-]+$"
CONVENTION_REF_PATTERN = r"^[a-z0-9-]+/[a-z0-9-]+$"
PLACEHOLDER_NAME_PATTERN = r"^[a-zA-Z][a-zA-Z0-9]*$"
PLACEHOLDER_VALUE_PATTERN = r"^[a-zA-Z0-9_-]+$"
SOURCE_PREFIX_PATTERN = r"^[a-z0-9-]+$"

ConventionName = Annotated[str, StringConstraints(pattern=CONVENTION_NAME_PATTERN)]
ConventionRef = Annotated[str, StringConstraints(pattern=CONVENTION_REF_PATTERN)]
PlaceholderName = Annotated[str, StringConstraints(pattern=PLACEHOLDER_NAME_PATTERN)]
PlaceholderVal = Annotated[str, StringConstraints(pattern=PLACEHOLDER_VALUE_PATTERN)]
SourcePrefix = Annotated[str, StringConstraints(pattern=SOURCE_PREFIX_PATTERN)]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
NonEmptyRegexList = Annotated[list[NonEmptyString], Field(min_length=1)]

PlaceholdersMap = dict[PlaceholderName, PlaceholderVal]
Severity = Literal["error", "warning"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _predicate_registry_from_context(context: object) -> object | None:
    if isinstance(context, Mapping):
        return context.get("predicate_registry")
    return None
