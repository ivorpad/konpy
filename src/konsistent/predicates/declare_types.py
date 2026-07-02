from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity
from konsistent.predicates.declaration_utils import (
    DeclarationCheckContext,
    create_exported_declaration_diagnostic,
    create_missing_declaration_diagnostic,
    find_declaration_symbol,
    is_declaration_symbol_exported,
    resolve_definition_name,
)
from konsistent.python_ast.structure import PyFileStructure


def check_declare_types(
    *,
    expected: list[Any],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    check_context = DeclarationCheckContext(
        context=context,
        convention_name=convention_name,
        predicate_name="declareTypes",
        severity=severity,
    )

    for entry in expected:
        name = resolve_definition_name(entry=entry, context=context)
        symbol = find_declaration_symbol(
            structure=structure,
            kinds=("type", "protocol"),
            name=name,
        )
        if symbol is None:
            diagnostics.append(
                create_missing_declaration_diagnostic(
                    check_context=check_context,
                    label="type",
                    name=name,
                )
            )
        elif is_declaration_symbol_exported(structure=structure, symbol=symbol):
            diagnostics.append(
                create_exported_declaration_diagnostic(
                    check_context=check_context,
                    label="type",
                    symbol=symbol,
                )
            )

    return diagnostics
