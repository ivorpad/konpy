from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity
from konsistent.predicates._utils import check_function_signature, definition_name
from konsistent.predicates.declaration_utils import (
    DeclarationCheckContext,
    create_exported_declaration_diagnostic,
    create_missing_declaration_diagnostic,
    find_declaration_symbol,
    is_declaration_symbol_exported,
)
from konsistent.python_ast.structure import PyFileStructure


def check_declare_functions(
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
        predicate_name="declareFunctions",
        severity=severity,
    )

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = definition_name(definition, context)
        symbol = find_declaration_symbol(
            structure=structure,
            kinds=("function",),
            name=name,
        )
        function_info = next(
            (function for function in structure.functions if function.name == name),
            None,
        )

        if symbol is None or function_info is None:
            diagnostics.append(
                create_missing_declaration_diagnostic(
                    check_context=check_context,
                    label="function",
                    name=name,
                )
            )
            continue

        if is_declaration_symbol_exported(structure=structure, symbol=symbol):
            diagnostics.append(
                create_exported_declaration_diagnostic(
                    check_context=check_context,
                    label="function",
                    symbol=symbol,
                )
            )
            continue

        diagnostics.extend(
            check_function_signature(
                predicate_name="declareFunctions",
                function_info=function_info,
                definition=definition,
                resolved_name=name,
                context=context,
                convention_name=convention_name,
                severity=severity,
            )
        )

    return diagnostics
