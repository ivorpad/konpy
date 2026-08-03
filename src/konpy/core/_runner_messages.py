"""Forbidden-predicate name resolution and human-readable `mustNot` messages."""

from __future__ import annotations

from collections.abc import Mapping

from konpy.core.context import PredicateContext
from konpy.predicates.import_source import ImportKind, ImportSourceGroup
from konpy.predicates.registry import PredicateRegistry

_IMPORT_SOURCE_GROUPS: dict[str, tuple[ImportSourceGroup, ImportKind]] = {
    "importFromCurrentDir": ("currentDir", "value"),
    "importFromParents": ("parents", "value"),
    "importFromExternals": ("externals", "value"),
    "importTypesFromCurrentDir": ("currentDir", "type"),
    "importTypesFromParents": ("parents", "type"),
    "importTypesFromExternals": ("externals", "type"),
}


def _get_value(obj: object, key: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _resolve_entry_name(
    *,
    value: object,
    context: PredicateContext,
) -> str:
    if isinstance(value, str):
        return context.resolve_template(value)

    name = _get_value(value, "name")
    if isinstance(name, str):
        return context.resolve_template(name)

    return "unknown"


def _format_forbidden_message(
    *,
    key: str,
    value: object,
    context: PredicateContext,
    predicate_registry: PredicateRegistry,
) -> str:
    plugin_message_provider = predicate_registry.plugin_forbidden_messages.get(key)
    if plugin_message_provider is not None:
        return plugin_message_provider(value, context)

    name = _resolve_entry_name(value=value, context=context)

    match key:
        case "haveType":
            return f'Forbidden path type "{value}"'
        case "haveFiles":
            return f'Forbidden file "{context.resolve_template(str(value))}"'
        case "matchContent":
            return f'Forbidden content matching regex "{value}"'
        case "havePairedFile":
            return f'Forbidden paired file "{context.resolve_template(str(value))}"'
        case "declareTypes":
            return f'Forbidden type declaration "{name}"'
        case "declareConstants":
            return f'Forbidden constant declaration "{name}"'
        case "declareFunctions":
            return f'Forbidden function declaration "{name}"'
        case "declareInterfaces":
            return f'Forbidden interface declaration "{name}"'
        case "declareClasses":
            return f'Forbidden class declaration "{name}"'
        case "export":
            return f'Forbidden export "{name}"'
        case "exportTypes":
            return f'Forbidden type export "{name}"'
        case "exportConstants":
            return f'Forbidden constant export "{name}"'
        case "exportFunctions":
            return f'Forbidden function export "{name}"'
        case "exportInterfaces":
            return f'Forbidden interface export "{name}"'
        case "exportClasses":
            return f'Forbidden class export "{name}"'
        case "import":
            return f'Forbidden import "{name}"'
        case "importFrom":
            return f'Forbidden import from "{context.resolve_template(str(value))}"'
        case "importTypes":
            return f'Forbidden type import "{name}"'
        case "importFromCurrentDir":
            if value is False:
                return "Missing import from current directory is not allowed"
            return "Forbidden import from current directory"
        case "importFromParents":
            if value is False:
                return "Missing import from parent directories is not allowed"
            return "Forbidden import from parent directories"
        case "importFromExternals":
            if value is False:
                return "Missing import from external packages is not allowed"
            return "Forbidden import from external packages"
        case "importTypesFromCurrentDir":
            if value is False:
                return "Missing type import from current directory is not allowed"
            return "Forbidden type import from current directory"
        case "importTypesFromParents":
            if value is False:
                return "Missing type import from parent directories is not allowed"
            return "Forbidden type import from parent directories"
        case "importTypesFromExternals":
            if value is False:
                return "Missing type import from external packages is not allowed"
            return "Forbidden type import from external packages"
        case "useDeclarationOrder":
            entries = value if isinstance(value, list) else [str(value)]
            resolved = [context.resolve_template(entry) for entry in entries]
            joined = '", "'.join(resolved)
            return f'Forbidden declaration order "{joined}"'
        case "areBarrelFiles":
            if value is False:
                return "Forbidden non-barrel file"
            return "Forbidden barrel file"
        case "haveDocstrings":
            return "Forbidden docstring coverage"
        case "annotateFunctions":
            return "Forbidden function annotation coverage"
        case _:
            return f"Forbidden {key}"
