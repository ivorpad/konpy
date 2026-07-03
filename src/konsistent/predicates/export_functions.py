from __future__ import annotations

from konsistent.config.schema import FunctionDefinitionV1
from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import check_function_signature, definition_name
from konsistent.python_ast.structure import PyFileStructure


def check_export_functions(
    *,
    expected: list[str | FunctionDefinitionV1],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected function is exported with a matching signature."""
    diagnostics: list[Diagnostic] = []

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = definition_name(definition, context)
        is_exported = any(
            export.name == name and not export.is_type
            for export in structure.exports
        )
        function_info = next(
            (function for function in structure.functions if function.name == name),
            None,
        )

        if not is_exported or function_info is None:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="exportFunctions",
                    message=f'Missing export function "{name}"',
                    convention_name=convention_name,
                    severity=severity,
                )
            )
            continue

        diagnostics.extend(
            check_function_signature(
                predicate_name="exportFunctions",
                function_info=function_info,
                definition=definition,
                resolved_name=name,
                context=context,
                convention_name=convention_name,
                severity=severity,
            )
        )

    return diagnostics
