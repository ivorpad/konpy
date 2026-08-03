"""Placeholder-usage scanning across a single must/mustNot predicate block.

Walks the builtin predicate keys (haveFiles, declareX, exportX, importX,
useDeclarationOrder) plus any plugin-registered predicate keys, looking for
${name} placeholder usages that aren't declared by the convention.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from konpy.config._placeholder_definition_usages import (
    _collect_usages_in_definition_list,
    _collect_usages_recursively,
)
from konpy.config._placeholder_shared import _push_string_usages, _Usage

if TYPE_CHECKING:
    # konpy.predicates.registry imports konpy.config.schema at module
    # level, so importing it unconditionally here would cycle back through
    # this package's __init__; PredicateRegistry is only used in annotations.
    from konpy.predicates.registry import PredicateRegistry

_BUILTIN_PREDICATE_KEYS = {
    "annotateFunctions",
    "areBarrelFiles",
    "declareClasses",
    "declareConstants",
    "declareFunctions",
    "declareInterfaces",
    "declareTypes",
    "export",
    "exportClasses",
    "exportConstants",
    "exportFunctions",
    "exportInterfaces",
    "exportTypes",
    "haveDocstrings",
    "haveFiles",
    "havePairedFile",
    "haveType",
    "import",
    "importFrom",
    "importFromCurrentDir",
    "importFromExternals",
    "importFromParents",
    "importTypes",
    "importTypesFromCurrentDir",
    "importTypesFromExternals",
    "importTypesFromParents",
    "matchContent",
    "restrictAnnotations",
    "restrictBaseClasses",
    "restrictCalls",
    "restrictDecorators",
    "restrictDuplicateFunctions",
    "restrictFileLength",
    "restrictImports",
    "restrictRepeatedLiterals",
    "useDeclarationOrder",
}


def _collect_usages_in_predicates(
    *,
    predicates: Mapping[str, object],
    prefix: str,
    declared: set[str],
    usages: list[_Usage],
    predicate_registry: PredicateRegistry | None,
) -> None:
    have_files = predicates.get("haveFiles", [])
    for file_entry in have_files if isinstance(have_files, Sequence) else []:
        _push_string_usages(
            value=file_entry,
            key=f"{prefix}.haveFiles",
            declared=declared,
            usages=usages,
        )

    if "havePairedFile" in predicates:
        _push_string_usages(
            value=predicates["havePairedFile"],
            key=f"{prefix}.havePairedFile",
            declared=declared,
            usages=usages,
        )

    _collect_usages_in_definition_list(
        list_=predicates.get("declareTypes"),
        key=f"{prefix}.declareTypes",
        object_fields=("name",),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("declareConstants"),
        key=f"{prefix}.declareConstants",
        object_fields=("name",),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("declareFunctions"),
        key=f"{prefix}.declareFunctions",
        object_fields=("name", "receiveParamOfType", "returnValueOfType"),
        array_fields=("receiveParamsOfTypes",),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("declareInterfaces"),
        key=f"{prefix}.declareInterfaces",
        object_fields=("name",),
        extend_field=True,
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("declareClasses"),
        key=f"{prefix}.declareClasses",
        object_fields=("name",),
        extend_field=True,
        implement_field=True,
        declared=declared,
        usages=usages,
    )

    declaration_order = predicates.get("useDeclarationOrder", [])
    for name in declaration_order if isinstance(declaration_order, Sequence) else []:
        _push_string_usages(
            value=name,
            key=f"{prefix}.useDeclarationOrder",
            declared=declared,
            usages=usages,
        )

    _collect_usages_in_definition_list(
        list_=predicates.get("export"),
        key=f"{prefix}.export",
        object_fields=("name", "from"),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("exportTypes"),
        key=f"{prefix}.exportTypes",
        object_fields=("name", "from"),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("exportConstants"),
        key=f"{prefix}.exportConstants",
        object_fields=("name", "from"),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("exportFunctions"),
        key=f"{prefix}.exportFunctions",
        object_fields=("name", "receiveParamOfType", "returnValueOfType"),
        array_fields=("receiveParamsOfTypes",),
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("exportInterfaces"),
        key=f"{prefix}.exportInterfaces",
        object_fields=("name",),
        extend_field=True,
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("exportClasses"),
        key=f"{prefix}.exportClasses",
        object_fields=("name",),
        extend_field=True,
        implement_field=True,
        declared=declared,
        usages=usages,
    )
    _collect_usages_in_definition_list(
        list_=predicates.get("import"),
        key=f"{prefix}.import",
        object_fields=("name", "from"),
        declared=declared,
        usages=usages,
    )

    if "importFrom" in predicates:
        _push_string_usages(
            value=predicates["importFrom"],
            key=f"{prefix}.importFrom",
            declared=declared,
            usages=usages,
        )

    _collect_usages_in_definition_list(
        list_=predicates.get("importTypes"),
        key=f"{prefix}.importTypes",
        object_fields=("name", "from"),
        declared=declared,
        usages=usages,
    )

    _collect_usages_in_plugin_predicates(
        predicates=predicates,
        prefix=prefix,
        declared=declared,
        usages=usages,
        predicate_registry=predicate_registry,
    )


def _collect_usages_in_plugin_predicates(
    *,
    predicates: Mapping[str, object],
    prefix: str,
    declared: set[str],
    usages: list[_Usage],
    predicate_registry: PredicateRegistry | None,
) -> None:
    plugin_validate_placeholders = (
        predicate_registry.plugin_validate_placeholders if predicate_registry is not None else {}
    )
    plugin_value_adapters = (
        predicate_registry.plugin_value_adapters if predicate_registry is not None else {}
    )

    for key, value in predicates.items():
        if key in _BUILTIN_PREDICATE_KEYS:
            continue

        if predicate_registry is not None and key not in plugin_value_adapters:
            continue

        if plugin_validate_placeholders.get(key, True) is False:
            continue

        _collect_usages_recursively(
            value=value,
            key=f"{prefix}.{key}",
            declared=declared,
            usages=usages,
        )


__all__: list[str] = []
