from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from konsistent.config._schema_types import (
    NonEmptyRegexList,
    NonEmptyString,
    _predicate_registry_from_context,
    _StrictModel,
)


class ExportDefinitionV1(_StrictModel):
    """An export reference: a bare name, optionally re-exported from another module."""

    name: str
    from_: str | None = Field(default=None, alias="from")


class DeclarationDefinitionV1(_StrictModel):
    """A bare name reference to a declared type, constant, or function."""

    name: str


class ImportDefinitionV1(_StrictModel):
    """An import reference: a bare name, optionally imported from another module."""

    name: str
    from_: str | None = Field(default=None, alias="from")


class FunctionDefinitionV1(_StrictModel):
    """A function/method signature reference used by declare/export predicates."""

    name: str
    receiveParamOfType: str | None = None
    """Deprecated: use receiveParamsOfTypes instead."""
    receiveParamsOfTypes: list[str] | None = None
    returnValueOfType: str | None = None


class ExtendObjectV1(_StrictModel):
    """A base-type reference with an ``allowOmissions`` escape hatch."""

    type: str
    allowOmissions: bool | None = None


ExtendDefinitionV1 = str | ExtendObjectV1


class InterfaceDefinitionV1(_StrictModel):
    """An interface/protocol reference, optionally extending another type."""

    name: str
    extend: ExtendDefinitionV1 | None = None


class ClassDefinitionV1(_StrictModel):
    """A class reference, optionally extending a base and implementing interfaces."""

    name: str
    extend: ExtendDefinitionV1 | None = None
    implement: list[ExtendDefinitionV1] | None = None


class HaveDocstringsOptionsV1(_StrictModel):
    """Per-target options for the ``haveDocstrings`` predicate."""

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
    """Per-target options for the ``annotateFunctions`` predicate."""

    returns: bool | None = None
    params: bool | None = None
    publicOnly: bool | None = None

    @model_validator(mode="after")
    def _requires_at_least_one_check(self) -> Self:
        if self.returns is False and self.params is False:
            raise ValueError("annotateFunctions requires at least one of returns or params")
        return self


class MustPredicatesV1(_StrictModel):
    """The full set of predicates a convention's ``must``/``mustNot`` block may declare."""

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
