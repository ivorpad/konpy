"""Config schema: pydantic v2 strict models mirroring the upstream zod schemas
(packages/convention/src/schemas.ts + packages/konpy/src/config/schema.ts).

Field names keep the verbatim camelCase JSON keys; Python keywords get a
trailing-underscore field with an alias (``import_``/``if_``/``for_``/
``from_``/``schema_``).

Models are defined across ``_schema_types``, ``_schema_predicates``, and
``_schema_conventions``; this module re-exports the public surface.
"""

from __future__ import annotations

from konpy.config._schema_conventions import (
    ConditionV1,
    ConfigV1,
    ConventionUseRefV1,
    ConventionV1,
    ForV1,
    HasFileConditionV1,
    MustBlockUseRefV1,
    MustBlockV1,
    PlaceholderSatisfiesConditionV1,
    RawConfigV1,
    RawHandWrittenConventionV1,
    ReusableConventionsPackageV1,
    ReusableConventionV1,
    UnusedCodeV1,
)
from konpy.config._schema_predicates import (
    AnnotateFunctionsOptionsV1,
    ClassDefinitionV1,
    DeclarationDefinitionV1,
    ExportDefinitionV1,
    ExtendDefinitionV1,
    ExtendObjectV1,
    FunctionDefinitionV1,
    HaveDocstringsOptionsV1,
    ImportDefinitionV1,
    InterfaceDefinitionV1,
    MustPredicatesV1,
    RestrictAnnotationsOptionsV1,
    RestrictDuplicateFunctionsOptionsV1,
    RestrictRepeatedLiteralsOptionsV1,
)
from konpy.config._schema_types import (
    CONVENTION_NAME_PATTERN,
    CONVENTION_REF_PATTERN,
    PLACEHOLDER_NAME_PATTERN,
    PLACEHOLDER_VALUE_PATTERN,
    SOURCE_PREFIX_PATTERN,
    ConventionName,
    ConventionRef,
    NonEmptyRegexList,
    NonEmptyString,
    PlaceholderName,
    PlaceholdersMap,
    PlaceholderVal,
    Severity,
    SourcePrefix,
)

__all__ = [
    "CONVENTION_NAME_PATTERN",
    "CONVENTION_REF_PATTERN",
    "PLACEHOLDER_NAME_PATTERN",
    "PLACEHOLDER_VALUE_PATTERN",
    "SOURCE_PREFIX_PATTERN",
    "AnnotateFunctionsOptionsV1",
    "ClassDefinitionV1",
    "ConditionV1",
    "ConfigV1",
    "ConventionName",
    "ConventionRef",
    "ConventionUseRefV1",
    "ConventionV1",
    "DeclarationDefinitionV1",
    "ExportDefinitionV1",
    "ExtendDefinitionV1",
    "ExtendObjectV1",
    "ForV1",
    "FunctionDefinitionV1",
    "HasFileConditionV1",
    "HaveDocstringsOptionsV1",
    "ImportDefinitionV1",
    "InterfaceDefinitionV1",
    "MustBlockUseRefV1",
    "MustBlockV1",
    "MustPredicatesV1",
    "NonEmptyRegexList",
    "NonEmptyString",
    "PlaceholderName",
    "PlaceholderSatisfiesConditionV1",
    "PlaceholderVal",
    "PlaceholdersMap",
    "RawConfigV1",
    "RawHandWrittenConventionV1",
    "RestrictAnnotationsOptionsV1",
    "RestrictDuplicateFunctionsOptionsV1",
    "RestrictRepeatedLiteralsOptionsV1",
    "ReusableConventionV1",
    "ReusableConventionsPackageV1",
    "Severity",
    "SourcePrefix",
    "UnusedCodeV1",
]
