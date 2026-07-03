from __future__ import annotations

from konpy.config.schema import DeclarationDefinitionV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity
from konpy.predicates.declaration_utils import (
    DeclarationCheckContext,
    create_exported_declaration_diagnostic,
    create_missing_declaration_diagnostic,
    find_declaration_symbol,
    is_declaration_symbol_exported,
    resolve_definition_name,
)
from konpy.python_ast.structure import PyFileStructure


def check_declare_constants(
    *,
    expected: list[str | DeclarationDefinitionV1],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected constant is locally declared and unexported."""
    diagnostics: list[Diagnostic] = []
    check_context = DeclarationCheckContext(
        context=context,
        convention_name=convention_name,
        predicate_name="declareConstants",
        severity=severity,
    )

    for entry in expected:
        name = resolve_definition_name(entry=entry, context=context)
        symbol = find_declaration_symbol(
            structure=structure,
            kinds=("const",),
            name=name,
        )
        if symbol is None:
            diagnostics.append(
                create_missing_declaration_diagnostic(
                    check_context=check_context,
                    label="constant",
                    name=name,
                )
            )
        elif is_declaration_symbol_exported(structure=structure, symbol=symbol):
            diagnostics.append(
                create_exported_declaration_diagnostic(
                    check_context=check_context,
                    label="constant",
                    symbol=symbol,
                )
            )

    return diagnostics
