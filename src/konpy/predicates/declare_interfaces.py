from __future__ import annotations

from konpy.config.schema import ExtendDefinitionV1, InterfaceDefinitionV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import get_value, resolve_extend_type
from konpy.predicates.declaration_utils import (
    DeclarationCheckContext,
    create_exported_declaration_diagnostic,
    create_missing_declaration_diagnostic,
    find_declaration_symbol,
    is_declaration_symbol_exported,
)
from konpy.python_ast.structure import ExtendsClauseInfo, PyFileStructure


def _allow_omissions(extend: ExtendDefinitionV1 | None) -> bool:
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


def check_declare_interfaces(
    *,
    expected: list[str | InterfaceDefinitionV1],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected interface is locally declared, unexported, and extends the base."""
    diagnostics: list[Diagnostic] = []
    check_context = DeclarationCheckContext(
        context=context,
        convention_name=convention_name,
        predicate_name="declareInterfaces",
        severity=severity,
    )

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = context.resolve_template(str(get_value(definition, "name", "")))
        symbol = find_declaration_symbol(
            structure=structure,
            kinds=("protocol",),
            name=name,
        )
        interface_info = next(
            (interface for interface in structure.interfaces if interface.name == name),
            None,
        )

        if symbol is None or interface_info is None:
            diagnostics.append(
                create_missing_declaration_diagnostic(
                    check_context=check_context,
                    label="interface",
                    name=name,
                )
            )
            continue

        if is_declaration_symbol_exported(structure=structure, symbol=symbol):
            diagnostics.append(
                create_exported_declaration_diagnostic(
                    check_context=check_context,
                    label="interface",
                    symbol=symbol,
                )
            )
            continue

        extend = get_value(definition, "extend")
        expected_extend = resolve_extend_type(extend, context)
        if expected_extend is None:
            continue

        if _matches_extend(interface_info.extends, expected_extend, _allow_omissions(extend)):
            continue

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="declareInterfaces",
                message=f'Interface "{name}" must extend "{expected_extend}"',
                convention_name=convention_name,
                line=interface_info.pos.line,
                column=interface_info.pos.column,
                severity=severity,
            )
        )

    return diagnostics
