from __future__ import annotations

from konpy.config.schema import ExportDefinitionV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import definition_name
from konpy.python_ast.structure import PyFileStructure


def check_export_constants(
    *,
    expected: list[str | ExportDefinitionV1],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected name is exported as a module-level constant."""
    diagnostics: list[Diagnostic] = []

    for entry in expected:
        name = definition_name(entry, context)
        found = any(
            export.name == name and export.kind == "const" and not export.is_type
            for export in structure.exports
        )
        if found:
            continue

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="exportConstants",
                message=f'Missing export constant "{name}"',
                convention_name=convention_name,
                severity=severity,
                expected=name,
                fix_hint=(
                    f"Define a public module-level constant `{name} = ...` in {context.path}."
                ),
            )
        )

    return diagnostics
