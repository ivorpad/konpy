from __future__ import annotations

from konpy.config.schema import InterfaceDefinitionV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import definition_name, get_value, resolve_extend_type
from konpy.python_ast.structure import ExtendsClauseInfo, PyFileStructure


def _allow_omissions(extend: object) -> bool:
    if isinstance(extend, str):
        return False
    return bool(get_value(extend, "allowOmissions", False))


def _matches_extend(
    extends: tuple[ExtendsClauseInfo, ...],
    expected: str,
    allow_omissions: bool,
) -> bool:
    if any(entry.name == expected for entry in extends):
        return True
    return allow_omissions and any(
        entry.type_arguments and entry.type_arguments[0] == expected
        for entry in extends
    )


def check_export_interfaces(
    *,
    expected: list[str | InterfaceDefinitionV1],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected interface is exported and extends the right base."""
    diagnostics: list[Diagnostic] = []

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = definition_name(definition, context)
        is_exported = any(
            export.name == name and export.kind in {"protocol", "re-export"}
            for export in structure.exports
        )
        interface_info = next(
            (interface for interface in structure.interfaces if interface.name == name),
            None,
        )

        if not is_exported:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="exportInterfaces",
                    message=f'Missing export interface "{name}"',
                    convention_name=convention_name,
                    severity=severity,
                )
            )
            continue

        extend = get_value(definition, "extend")
        expected_extend = resolve_extend_type(extend, context)
        if expected_extend is None or interface_info is None:
            continue

        if _matches_extend(interface_info.extends, expected_extend, _allow_omissions(extend)):
            continue

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="exportInterfaces",
                message=f'Interface "{name}" must extend "{expected_extend}"',
                convention_name=convention_name,
                line=interface_info.pos.line,
                column=interface_info.pos.column,
                severity=severity,
            )
        )

    return diagnostics
