from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import definition_name
from konsistent.python_ast.structure import PyFileStructure


def check_export_constants(
    *,
    expected: list[Any],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
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
            )
        )

    return diagnostics
