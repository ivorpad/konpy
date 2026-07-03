from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from konpy.config._schema_predicates import MustPredicatesV1
from konpy.config._schema_types import (
    ConventionName,
    ConventionRef,
    PlaceholdersMap,
    Severity,
    SourcePrefix,
    _StrictModel,
)


class HasFileConditionV1(_StrictModel):
    """A condition satisfied when the given file exists."""

    hasFile: str


class PlaceholderSatisfiesConditionV1(_StrictModel):
    """A condition satisfied when a placeholder value matches a pattern."""

    placeholderSatisfies: str


ConditionV1 = HasFileConditionV1 | PlaceholderSatisfiesConditionV1


class ForV1(_StrictModel):
    """Scopes a ``must``/``mustNot`` block to a subset of files within a convention's paths."""

    files: str | list[str]


class _RequiresMustOrMustNot(_StrictModel):
    @model_validator(mode="after")
    def _check_must_or_must_not(self) -> Self:
        if getattr(self, "must", None) is None and getattr(self, "mustNot", None) is None:
            raise ValueError('requires at least one of "must" or "mustNot"')
        return self


class MustBlockV1(_RequiresMustOrMustNot):
    """A single hand-written ``must``/``mustNot`` predicate block."""

    name: ConventionName | None = None
    description: str | None = None
    hint: str | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    excludeFiles: list[str] | None = None
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ReusableConventionV1(_RequiresMustOrMustNot):
    """A convention defined for reuse via ``conventionSources``/``extends`` references."""

    name: ConventionName
    description: str
    hint: str | None = None
    severity: Severity | None = None
    paths: str | list[str] | None = None
    excludeFiles: list[str] | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ReusableConventionsPackageV1(_StrictModel):
    """A package of reusable conventions, as published for ``extends``/``use`` references."""

    conventionSpecVersion: Literal["v1"]
    conventions: list[ReusableConventionV1]


class MustBlockUseRefV1(_StrictModel):
    """A ``must``/``mustNot`` block that references a reusable convention by name."""

    use: ConventionRef
    name: ConventionName | None = None
    description: str | None = None
    hint: str | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    excludeFiles: list[str] | None = None
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ConventionV1(_RequiresMustOrMustNot):
    """A fully-materialized convention (after reference expansion)."""

    name: ConventionName | None = None
    description: str | None = None
    hint: str | None = None
    severity: Severity | None = None
    excludeFiles: list[str] | None = None
    paths: str | list[str]
    placeholders: PlaceholdersMap | None = None
    must: MustPredicatesV1 | list[MustBlockV1] | None = None
    mustNot: MustPredicatesV1 | None = None


class RawHandWrittenConventionV1(_RequiresMustOrMustNot):
    """A hand-written convention as it appears in ``konpy.json``, before expansion."""

    name: ConventionName | None = None
    description: str | None = None
    hint: str | None = None
    severity: Severity | None = None
    excludeFiles: list[str] | None = None
    paths: str | list[str]
    placeholders: PlaceholdersMap | None = None
    must: MustPredicatesV1 | list[ConventionRef | MustBlockV1 | MustBlockUseRefV1] | None = None
    mustNot: MustPredicatesV1 | None = None


class ConventionUseRefV1(_StrictModel):
    """A top-level convention entry that references a reusable convention by name."""

    use: ConventionRef
    severity: Severity | None = None
    paths: str | list[str] | None = None
    placeholders: PlaceholdersMap | None = None
    excludeFiles: list[str] | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class UnusedCodeV1(_StrictModel):
    """Optional ``unusedCode`` rule config (M10 unused-code detection).

    All fields are optional; engine-level defaults and framework presets are
    applied in ``konpy.unused.engine`` rather than in this model.
    """

    include: list[str] | None = None
    testGlobs: list[str] | None = None
    entrypointFiles: list[str] | None = None
    registryDecorators: list[str] | None = None
    hookNames: list[str] | None = None
    modelBases: list[str] | None = None
    allow: list[str] | None = None
    severity: Severity | None = None


class RawConfigV1(_StrictModel):
    """The konpy.json file as written (conventions may be references)."""

    schema_: str | None = Field(default=None, alias="$schema")
    version: Literal["v1"]
    extends: list[str] | None = None
    disable: list[ConventionName] | None = None
    plugins: list[str] | None = None
    kebabToPascalMap: dict[str, str] | None = None
    kebabToCamelMap: dict[str, str] | None = None
    conventionSources: dict[SourcePrefix, str] | None = None
    conventions: list[ConventionRef | ConventionUseRefV1 | RawHandWrittenConventionV1]
    unusedCode: UnusedCodeV1 | None = None


class ConfigV1(_StrictModel):
    """The loaded config after reference expansion and placeholder injection."""

    schema_: str | None = Field(default=None, alias="$schema")
    version: Literal["v1"]
    plugins: list[str] | None = None
    kebabToPascalMap: dict[str, str] | None = None
    kebabToCamelMap: dict[str, str] | None = None
    conventionSources: dict[str, str] | None = None
    conventions: list[ConventionV1]
    unusedCode: UnusedCodeV1 | None = None
