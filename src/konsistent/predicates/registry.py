from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter

from konsistent.config.schema import MustPredicatesV1
from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity
from konsistent.core.filesystem import FileSystem
from konsistent.plugin import PredicatePlugin
from konsistent.predicates.annotate_functions import check_annotate_functions
from konsistent.predicates.are_barrel_files import check_are_barrel_files
from konsistent.predicates.declare_classes import check_declare_classes
from konsistent.predicates.declare_constants import check_declare_constants
from konsistent.predicates.declare_functions import check_declare_functions
from konsistent.predicates.declare_interfaces import check_declare_interfaces
from konsistent.predicates.declare_types import check_declare_types
from konsistent.predicates.export import check_export
from konsistent.predicates.export_classes import check_export_classes
from konsistent.predicates.export_constants import check_export_constants
from konsistent.predicates.export_functions import check_export_functions
from konsistent.predicates.export_interfaces import check_export_interfaces
from konsistent.predicates.export_types import check_export_types
from konsistent.predicates.have_docstrings import check_have_docstrings
from konsistent.predicates.have_files import check_have_files
from konsistent.predicates.have_paired_file import check_have_paired_file
from konsistent.predicates.have_type import check_have_type
from konsistent.predicates.import_ import check_import
from konsistent.predicates.import_from import check_import_from
from konsistent.predicates.import_source import check_import_source
from konsistent.predicates.import_types import check_import_types
from konsistent.predicates.match_content import check_match_content
from konsistent.predicates.use_declaration_order import check_use_declaration_order
from konsistent.python_ast.structure import PyFileStructure

AST_PREDICATES = frozenset(
    {
        "declareTypes",
        "declareConstants",
        "declareFunctions",
        "declareClasses",
        "declareInterfaces",
        "export",
        "exportTypes",
        "exportConstants",
        "exportFunctions",
        "exportClasses",
        "exportInterfaces",
        "import",
        "importFrom",
        "importTypes",
        "importFromCurrentDir",
        "importFromParents",
        "importFromExternals",
        "importTypesFromCurrentDir",
        "importTypesFromParents",
        "importTypesFromExternals",
        "useDeclarationOrder",
        "areBarrelFiles",
        "haveDocstrings",
        "annotateFunctions",
    }
)

ITEM_LEVEL_MUST_NOT_PREDICATES = frozenset(
    {
        "haveFiles",
        "matchContent",
        "declareTypes",
        "declareConstants",
        "declareFunctions",
        "declareInterfaces",
        "declareClasses",
        "export",
        "exportTypes",
        "exportConstants",
        "exportFunctions",
        "exportInterfaces",
        "exportClasses",
        "import",
        "importTypes",
    }
)

PredicateHandler = Callable[
    [
        Any,
        PredicateContext,
        FileSystem,
        PyFileStructure | None,
        str | None,
        DiagnosticSeverity | None,
    ],
    list[Diagnostic],
]
ForbiddenMessageProvider = Callable[[Any, PredicateContext], str]


@dataclass(frozen=True, kw_only=True)
class PluginOrigin:
    distribution_name: str
    entry_point_name: str


@dataclass(frozen=True, kw_only=True)
class PredicateRegistry:
    handlers: Mapping[str, PredicateHandler]
    ast_predicates: frozenset[str]
    item_level_must_not_predicates: frozenset[str]
    plugin_value_adapters: Mapping[str, TypeAdapter[Any]]
    plugin_forbidden_messages: Mapping[str, ForbiddenMessageProvider]
    plugin_validate_placeholders: Mapping[str, bool]
    plugin_origins: Mapping[str, PluginOrigin]

    def validation_context(self) -> dict[str, PredicateRegistry]:
        return {"predicate_registry": self}


def _require_structure(structure: PyFileStructure | None) -> PyFileStructure:
    if structure is None:
        raise ValueError("AST predicate requires a parsed PyFileStructure")
    return structure


def _ast(handler: Callable[..., list[Diagnostic]]) -> PredicateHandler:
    def wrapped(
        value: Any,
        context: PredicateContext,
        file_system: FileSystem,
        structure: PyFileStructure | None,
        convention_name: str | None,
        severity: DiagnosticSeverity | None,
    ) -> list[Diagnostic]:
        return handler(
            expected=value,
            context=context,
            structure=_require_structure(structure),
            convention_name=convention_name,
            severity=severity,
        )

    return wrapped


def _have_type(
    value: Any,
    context: PredicateContext,
    file_system: FileSystem,
    structure: PyFileStructure | None,
    convention_name: str | None,
    severity: DiagnosticSeverity | None,
) -> list[Diagnostic]:
    return check_have_type(
        expected=value,
        context=context,
        file_system=file_system,
        convention_name=convention_name,
        severity=severity,
    )


def _have_files(
    value: Any,
    context: PredicateContext,
    file_system: FileSystem,
    structure: PyFileStructure | None,
    convention_name: str | None,
    severity: DiagnosticSeverity | None,
) -> list[Diagnostic]:
    return check_have_files(
        expected=value,
        context=context,
        convention_name=convention_name,
        severity=severity,
    )


def _match_content(
    value: Any,
    context: PredicateContext,
    file_system: FileSystem,
    structure: PyFileStructure | None,
    convention_name: str | None,
    severity: DiagnosticSeverity | None,
) -> list[Diagnostic]:
    return check_match_content(
        expected=value,
        context=context,
        file_system=file_system,
        convention_name=convention_name,
        severity=severity,
    )


def _have_paired_file(
    value: Any,
    context: PredicateContext,
    file_system: FileSystem,
    structure: PyFileStructure | None,
    convention_name: str | None,
    severity: DiagnosticSeverity | None,
) -> list[Diagnostic]:
    return check_have_paired_file(
        expected=value,
        context=context,
        file_system=file_system,
        convention_name=convention_name,
        severity=severity,
    )


def _import_source(group: str, import_kind: str) -> PredicateHandler:
    def wrapped(
        value: Any,
        context: PredicateContext,
        file_system: FileSystem,
        structure: PyFileStructure | None,
        convention_name: str | None,
        severity: DiagnosticSeverity | None,
    ) -> list[Diagnostic]:
        predicate_name = {
            ("currentDir", "value"): "importFromCurrentDir",
            ("parents", "value"): "importFromParents",
            ("externals", "value"): "importFromExternals",
            ("currentDir", "type"): "importTypesFromCurrentDir",
            ("parents", "type"): "importTypesFromParents",
            ("externals", "type"): "importTypesFromExternals",
        }[(group, import_kind)]

        return check_import_source(
            expected=value,
            predicate_name=predicate_name,
            group=group,
            import_kind=import_kind,
            context=context,
            structure=_require_structure(structure),
            convention_name=convention_name,
            severity=severity,
        )

    return wrapped


PREDICATE_HANDLERS: dict[str, PredicateHandler] = {
    "haveType": _have_type,
    "haveFiles": _have_files,
    "matchContent": _match_content,
    "havePairedFile": _have_paired_file,
    "declareTypes": _ast(check_declare_types),
    "declareConstants": _ast(check_declare_constants),
    "declareFunctions": _ast(check_declare_functions),
    "declareInterfaces": _ast(check_declare_interfaces),
    "declareClasses": _ast(check_declare_classes),
    "export": _ast(check_export),
    "exportTypes": _ast(check_export_types),
    "exportConstants": _ast(check_export_constants),
    "exportFunctions": _ast(check_export_functions),
    "exportInterfaces": _ast(check_export_interfaces),
    "exportClasses": _ast(check_export_classes),
    "import": _ast(check_import),
    "importFrom": _ast(check_import_from),
    "importTypes": _ast(check_import_types),
    "importFromCurrentDir": _import_source("currentDir", "value"),
    "importFromParents": _import_source("parents", "value"),
    "importFromExternals": _import_source("externals", "value"),
    "importTypesFromCurrentDir": _import_source("currentDir", "type"),
    "importTypesFromParents": _import_source("parents", "type"),
    "importTypesFromExternals": _import_source("externals", "type"),
    "useDeclarationOrder": _ast(check_use_declaration_order),
    "areBarrelFiles": _ast(check_are_barrel_files),
    "haveDocstrings": _ast(check_have_docstrings),
    "annotateFunctions": _ast(check_annotate_functions),
}


def builtin_predicate_registry() -> PredicateRegistry:
    return PredicateRegistry(
        handlers=dict(PREDICATE_HANDLERS),
        ast_predicates=frozenset(AST_PREDICATES),
        item_level_must_not_predicates=frozenset(ITEM_LEVEL_MUST_NOT_PREDICATES),
        plugin_value_adapters={},
        plugin_forbidden_messages={},
        plugin_validate_placeholders={},
        plugin_origins={},
    )


def validation_context(registry: PredicateRegistry) -> dict[str, PredicateRegistry]:
    return registry.validation_context()


def wrap_plugin_handler(plugin: PredicatePlugin) -> PredicateHandler:
    def wrapped(
        value: Any,
        context: PredicateContext,
        file_system: FileSystem,
        structure: PyFileStructure | None,
        convention_name: str | None,
        severity: DiagnosticSeverity | None,
    ) -> list[Diagnostic]:
        del file_system
        return plugin.handler(
            expected=value,
            context=context,
            structure=structure,
            convention_name=convention_name,
            severity=severity,
        )

    return wrapped


def iter_predicate_items(must: MustPredicatesV1) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for field_name, field in type(must).model_fields.items():
        value = getattr(must, field_name)
        if value is not None:
            items.append((field.alias or field_name, value))

    for key, value in (must.model_extra or {}).items():
        items.append((key, value))

    return items


__all__ = [
    "AST_PREDICATES",
    "ITEM_LEVEL_MUST_NOT_PREDICATES",
    "PREDICATE_HANDLERS",
    "ForbiddenMessageProvider",
    "PluginOrigin",
    "PredicateHandler",
    "PredicateRegistry",
    "builtin_predicate_registry",
    "iter_predicate_items",
    "validation_context",
    "wrap_plugin_handler",
]
