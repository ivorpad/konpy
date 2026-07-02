from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from konsistent.config.errors import Err, Ok, Result
from konsistent.config.schema import ConventionV1

USAGE_REGEX = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9]*)")
DECLARATION_REGEX = re.compile(
    r"\{([a-zA-Z][a-zA-Z0-9]*)(?::[a-zA-Z][a-zA-Z0-9]*(?:\([^}]*\))?)?\}"
)

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
    "useDeclarationOrder",
}


def validate_placeholders(
    *,
    conventions: Sequence[ConventionV1],
    identifiers: Sequence[str],
    predicate_registry: Any | None = None,
) -> Result[None]:
    errors: list[str] = []

    for index, convention in enumerate(conventions):
        convention_data = _to_alias_dict(convention)
        identifier = identifiers[index] if index < len(identifiers) else f"conventions[{index}]"

        declared_from_paths = _collect_declarations(convention_data["paths"])
        declared = set(declared_from_paths)

        for name in convention_data.get("placeholders", {}):
            if name in declared_from_paths:
                errors.append(
                    f'Convention "{identifier}" declares placeholder "{name}" both in paths '
                    f'(as "{{{name}}}") and in placeholders. Pick one.'
                )
                continue
            declared.add(name)

        usages = _collect_usages_in_assertions(
            must=convention_data.get("must"),
            must_not=convention_data.get("mustNot"),
            declared_outer=declared,
            predicate_registry=predicate_registry,
        )

        reported: set[str] = set()
        for usage in usages:
            if usage.name in reported:
                continue
            reported.add(usage.name)
            errors.append(
                f'Convention "{identifier}" references "${{{usage.name}}}" in {usage.key}, '
                f'but neither paths nor placeholders declare "{{{usage.name}}}".'
            )

    if errors:
        return Err("\n".join(errors))
    return Ok(None)


class _Usage:
    def __init__(self, *, name: str, key: str) -> None:
        self.name = name
        self.key = key


def _collect_declarations(paths: str | Sequence[str]) -> set[str]:
    declared: set[str] = set()
    entries = [paths] if isinstance(paths, str) else paths
    for entry in entries:
        _add_declarations_from_string(value=entry, into=declared)
    return declared


def _add_declarations_from_string(*, value: str, into: set[str]) -> None:
    for match in DECLARATION_REGEX.finditer(value):
        into.add(match.group(1))


def _collect_usages_in_assertions(
    *,
    must: Any,
    must_not: Any,
    declared_outer: set[str],
    predicate_registry: Any | None,
) -> list[_Usage]:
    usages: list[_Usage] = []

    if isinstance(must, list):
        for block in must:
            _collect_usages_in_block(
                block=_to_alias_dict(block),
                declared_outer=declared_outer,
                usages=usages,
                predicate_registry=predicate_registry,
            )
    elif must is not None:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(must),
            prefix="must",
            declared=declared_outer,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    if must_not is not None:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(must_not),
            prefix="mustNot",
            declared=declared_outer,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    return usages


def _collect_usages_in_block(
    *,
    block: Mapping[str, Any],
    declared_outer: set[str],
    usages: list[_Usage],
    predicate_registry: Any | None,
) -> None:
    declared_here = set(declared_outer)

    if "for" in block:
        for_data = _to_alias_dict(block["for"])
        files = for_data["files"]
        file_entries = [files] if isinstance(files, str) else files
        for file_entry in file_entries:
            _add_declarations_from_string(value=file_entry, into=declared_here)
            _push_string_usages(
                value=file_entry,
                key="must.for.files",
                declared=declared_outer,
                usages=usages,
            )

    if "if" in block:
        if_data = _to_alias_dict(block["if"])
        if "hasFile" in if_data:
            _push_string_usages(
                value=if_data["hasFile"],
                key="must.if.hasFile",
                declared=declared_here,
                usages=usages,
            )
        elif "placeholderSatisfies" in if_data:
            _push_string_usages(
                value=if_data["placeholderSatisfies"],
                key="must.if.placeholderSatisfies",
                declared=declared_here,
                usages=usages,
            )

    for file_entry in block.get("excludeFiles", []):
        _push_string_usages(
            value=file_entry,
            key="must.excludeFiles",
            declared=declared_here,
            usages=usages,
        )

    if "must" in block:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(block["must"]),
            prefix="must",
            declared=declared_here,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    if "mustNot" in block:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(block["mustNot"]),
            prefix="mustNot",
            declared=declared_here,
            usages=usages,
            predicate_registry=predicate_registry,
        )


def _collect_usages_in_predicates(
    *,
    predicates: Mapping[str, Any],
    prefix: str,
    declared: set[str],
    usages: list[_Usage],
    predicate_registry: Any | None,
) -> None:
    for file_entry in predicates.get("haveFiles", []):
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

    for name in predicates.get("useDeclarationOrder", []):
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
    predicates: Mapping[str, Any],
    prefix: str,
    declared: set[str],
    usages: list[_Usage],
    predicate_registry: Any | None,
) -> None:
    plugin_validate_placeholders = (
        getattr(predicate_registry, "plugin_validate_placeholders", {})
        if predicate_registry is not None
        else {}
    )
    plugin_value_adapters = (
        getattr(predicate_registry, "plugin_value_adapters", {})
        if predicate_registry is not None
        else {}
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


def _collect_usages_recursively(
    *,
    value: Any,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    if isinstance(value, str):
        _push_string_usages(value=value, key=key, declared=declared, usages=usages)
        return

    if isinstance(value, BaseModel):
        _collect_usages_recursively(
            value=value.model_dump(by_alias=True, exclude_none=True),
            key=key,
            declared=declared,
            usages=usages,
        )
        return

    if isinstance(value, Mapping):
        for item in value.values():
            _collect_usages_recursively(
                value=item,
                key=key,
                declared=declared,
                usages=usages,
            )
        return

    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for item in value:
            _collect_usages_recursively(
                value=item,
                key=key,
                declared=declared,
                usages=usages,
            )


def _collect_usages_in_definition_list(
    *,
    list_: Sequence[Any] | None,
    key: str,
    object_fields: Sequence[str],
    declared: set[str],
    usages: list[_Usage],
    array_fields: Sequence[str] = (),
    extend_field: bool = False,
    implement_field: bool = False,
) -> None:
    if list_ is None:
        return

    for entry in list_:
        if isinstance(entry, str):
            _push_string_usages(value=entry, key=key, declared=declared, usages=usages)
            continue

        entry_data = _to_alias_dict(entry)
        for field in object_fields:
            value = entry_data.get(field)
            if isinstance(value, str):
                _push_string_usages(value=value, key=key, declared=declared, usages=usages)

        for field in array_fields:
            value = entry_data.get(field)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str):
                    _push_string_usages(value=item, key=key, declared=declared, usages=usages)

        if extend_field:
            _collect_extend_usages(
                value=entry_data.get("extend"),
                key=key,
                declared=declared,
                usages=usages,
            )

        if implement_field and isinstance(entry_data.get("implement"), list):
            for item in entry_data["implement"]:
                _collect_extend_usages(value=item, key=key, declared=declared, usages=usages)


def _collect_extend_usages(
    *,
    value: Any,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    if isinstance(value, str):
        _push_string_usages(value=value, key=key, declared=declared, usages=usages)
        return

    if isinstance(value, BaseModel | Mapping):
        value_data = _to_alias_dict(value)
        type_value = value_data.get("type")
        if isinstance(type_value, str):
            _push_string_usages(value=type_value, key=key, declared=declared, usages=usages)


def _push_string_usages(
    *,
    value: str,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    for match in USAGE_REGEX.finditer(value):
        name = match.group(1)
        if name not in declared:
            usages.append(_Usage(name=name, key=key))


def _to_alias_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping-like value, got {type(value).__name__}")


__all__ = ["DECLARATION_REGEX", "USAGE_REGEX", "validate_placeholders"]
