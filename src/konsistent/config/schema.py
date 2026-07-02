"""Config schema: pydantic v2 strict models mirroring the upstream zod schemas
(packages/convention/src/schemas.ts + packages/konsistent/src/config/schema.ts).

Field names keep the verbatim camelCase JSON keys; Python keywords get a
trailing-underscore field with an alias (``import_``/``if_``/``for_``/
``from_``/``schema_``).
"""

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

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


class ExportDefinitionV1(_StrictModel):
    name: str
    from_: str | None = Field(default=None, alias="from")


class DeclarationDefinitionV1(_StrictModel):
    name: str


class ImportDefinitionV1(_StrictModel):
    name: str
    from_: str | None = Field(default=None, alias="from")


class FunctionDefinitionV1(_StrictModel):
    name: str
    receiveParamOfType: str | None = None
    """Deprecated: use receiveParamsOfTypes instead."""
    receiveParamsOfTypes: list[str] | None = None
    returnValueOfType: str | None = None


class ExtendObjectV1(_StrictModel):
    type: str
    allowOmissions: bool | None = None


ExtendDefinitionV1 = str | ExtendObjectV1


class InterfaceDefinitionV1(_StrictModel):
    name: str
    extend: ExtendDefinitionV1 | None = None


class ClassDefinitionV1(_StrictModel):
    name: str
    extend: ExtendDefinitionV1 | None = None
    implement: list[ExtendDefinitionV1] | None = None


class HaveDocstringsOptionsV1(_StrictModel):
    modules: bool | None = None
    classes: bool | None = None
    functions: bool | None = None
    publicOnly: bool | None = None

    @model_validator(mode="after")
    def _requires_at_least_one_target(self) -> Self:
        if self.modules is False and self.classes is False and self.functions is False:
            raise ValueError(
                "haveDocstrings requires at least one of modules, classes, or functions"
            )
        return self


class AnnotateFunctionsOptionsV1(_StrictModel):
    returns: bool | None = None
    params: bool | None = None
    publicOnly: bool | None = None

    @model_validator(mode="after")
    def _requires_at_least_one_check(self) -> Self:
        if self.returns is False and self.params is False:
            raise ValueError("annotateFunctions requires at least one of returns or params")
        return self


class MustPredicatesV1(_StrictModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    haveType: Literal["file", "directory"] | None = None
    haveFiles: list[str] | None = None
    matchContent: NonEmptyRegexList | None = None
    havePairedFile: NonEmptyString | None = None
    declareTypes: list[str | DeclarationDefinitionV1] | None = None
    declareConstants: list[str | DeclarationDefinitionV1] | None = None
    declareFunctions: list[str | FunctionDefinitionV1] | None = None
    declareInterfaces: list[str | InterfaceDefinitionV1] | None = None
    declareClasses: list[str | ClassDefinitionV1] | None = None
    export: list[str | ExportDefinitionV1] | None = None
    exportTypes: list[str | ExportDefinitionV1] | None = None
    exportConstants: list[str | ExportDefinitionV1] | None = None
    exportFunctions: list[str | FunctionDefinitionV1] | None = None
    exportInterfaces: list[str | InterfaceDefinitionV1] | None = None
    exportClasses: list[str | ClassDefinitionV1] | None = None
    import_: list[str | ImportDefinitionV1] | None = Field(default=None, alias="import")
    importFrom: str | None = None
    importTypes: list[str | ImportDefinitionV1] | None = None
    importFromCurrentDir: bool | None = None
    importFromParents: bool | None = None
    importFromExternals: bool | None = None
    importTypesFromCurrentDir: bool | None = None
    importTypesFromParents: bool | None = None
    importTypesFromExternals: bool | None = None
    useDeclarationOrder: list[str] | None = None
    areBarrelFiles: bool | None = None
    haveDocstrings: Literal[True] | HaveDocstringsOptionsV1 | None = None
    annotateFunctions: Literal[True] | AnnotateFunctionsOptionsV1 | None = None

    @field_validator("matchContent")
    @classmethod
    def _validate_match_content_regexes(
        cls,
        value: NonEmptyRegexList | None,
    ) -> NonEmptyRegexList | None:
        if value is None:
            return None

        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f'invalid regex "{pattern}": {error}') from error

        return value

    @model_validator(mode="after")
    def _validate_plugin_predicates(self, info: ValidationInfo) -> Self:
        extra = self.model_extra
        if not extra:
            return self

        registry = _predicate_registry_from_context(info.context)
        adapters: Mapping[str, Any] = (
            getattr(registry, "plugin_value_adapters", {}) if registry is not None else {}
        )

        validated_extra: dict[str, Any] = {}
        for key, value in extra.items():
            adapter = adapters.get(key)
            if adapter is None:
                raise ValueError(f'unknown predicate key "{key}"')

            try:
                validated_extra[key] = adapter.validate_python(value)
            except Exception as error:
                raise ValueError(
                    f'plugin predicate "{key}" value is invalid: {error}'
                ) from error

        if self.__pydantic_extra__ is not None:
            self.__pydantic_extra__.update(validated_extra)

        return self


class HasFileConditionV1(_StrictModel):
    hasFile: str


class PlaceholderSatisfiesConditionV1(_StrictModel):
    placeholderSatisfies: str


ConditionV1 = HasFileConditionV1 | PlaceholderSatisfiesConditionV1


class ForV1(_StrictModel):
    files: str | list[str]


class _RequiresMustOrMustNot(_StrictModel):
    @model_validator(mode="after")
    def _check_must_or_must_not(self) -> Self:
        if getattr(self, "must", None) is None and getattr(self, "mustNot", None) is None:
            raise ValueError('requires at least one of "must" or "mustNot"')
        return self


class MustBlockV1(_RequiresMustOrMustNot):
    name: ConventionName | None = None
    description: str | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    excludeFiles: list[str] | None = None
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ReusableConventionV1(_RequiresMustOrMustNot):
    name: ConventionName
    description: str
    severity: Severity | None = None
    paths: str | list[str] | None = None
    excludeFiles: list[str] | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ReusableConventionsPackageV1(_StrictModel):
    conventionSpecVersion: Literal["v1"]
    conventions: list[ReusableConventionV1]


class MustBlockUseRefV1(_StrictModel):
    use: ConventionRef
    name: ConventionName | None = None
    description: str | None = None
    if_: ConditionV1 | None = Field(default=None, alias="if")
    for_: ForV1 | None = Field(default=None, alias="for")
    excludeFiles: list[str] | None = None
    must: MustPredicatesV1 | None = None
    mustNot: MustPredicatesV1 | None = None


class ConventionV1(_RequiresMustOrMustNot):
    """A fully-materialized convention (after reference expansion)."""

    name: ConventionName | None = None
    description: str | None = None
    severity: Severity | None = None
    excludeFiles: list[str] | None = None
    paths: str | list[str]
    placeholders: PlaceholdersMap | None = None
    must: MustPredicatesV1 | list[MustBlockV1] | None = None
    mustNot: MustPredicatesV1 | None = None


class RawHandWrittenConventionV1(_RequiresMustOrMustNot):
    name: ConventionName | None = None
    description: str | None = None
    severity: Severity | None = None
    excludeFiles: list[str] | None = None
    paths: str | list[str]
    placeholders: PlaceholdersMap | None = None
    must: MustPredicatesV1 | list[ConventionRef | MustBlockV1 | MustBlockUseRefV1] | None = None
    mustNot: MustPredicatesV1 | None = None


class ConventionUseRefV1(_StrictModel):
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
    applied in ``konsistent.unused.engine`` rather than in this model.
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
    """The konsistent.json file as written (conventions may be references)."""

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
