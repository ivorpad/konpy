from __future__ import annotations

from collections.abc import Callable

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity
from konpy.core.filesystem import FileSystem
from konpy.predicates.annotate_functions import check_annotate_functions
from konpy.predicates.are_barrel_files import check_are_barrel_files
from konpy.predicates.declare_classes import check_declare_classes
from konpy.predicates.declare_constants import check_declare_constants
from konpy.predicates.declare_functions import check_declare_functions
from konpy.predicates.declare_interfaces import check_declare_interfaces
from konpy.predicates.declare_types import check_declare_types
from konpy.predicates.export import check_export
from konpy.predicates.export_classes import check_export_classes
from konpy.predicates.export_constants import check_export_constants
from konpy.predicates.export_functions import check_export_functions
from konpy.predicates.export_interfaces import check_export_interfaces
from konpy.predicates.export_types import check_export_types
from konpy.predicates.have_docstrings import check_have_docstrings
from konpy.predicates.have_files import check_have_files
from konpy.predicates.have_paired_file import check_have_paired_file
from konpy.predicates.have_type import check_have_type
from konpy.predicates.import_ import check_import
from konpy.predicates.import_from import check_import_from
from konpy.predicates.import_source import check_import_source
from konpy.predicates.import_types import check_import_types
from konpy.predicates.match_content import check_match_content
from konpy.predicates.use_declaration_order import check_use_declaration_order
from konpy.python_ast.structure import PyFileStructure

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
        object,
        PredicateContext,
        FileSystem,
        PyFileStructure | None,
        str | None,
        DiagnosticSeverity | None,
    ],
    list[Diagnostic],
]


def _require_structure(structure: PyFileStructure | None) -> PyFileStructure:
    if structure is None:
        raise ValueError("AST predicate requires a parsed PyFileStructure")
    return structure


def _ast(handler: Callable[..., list[Diagnostic]]) -> PredicateHandler:
    def wrapped(
        value: object,
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
    value: object,
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
    value: object,
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
    value: object,
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
    value: object,
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
        value: object,
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
