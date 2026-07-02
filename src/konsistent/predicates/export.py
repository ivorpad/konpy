from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import definition_from, definition_name
from konsistent.python_ast.structure import PyFileStructure


def check_export(
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
        from_ = None if isinstance(entry, str) else definition_from(entry, context)
        found = any(
            export.name == name
            and not export.is_type
            and (from_ is None or export.from_ == from_)
            for export in structure.exports
        )
        if found:
            continue

        message = f'Missing export "{name}"'
        if from_:
            message = f'Missing export "{name}" from "{from_}"'

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="export",
                message=message,
                convention_name=convention_name,
                severity=severity,
            )
        )

    return diagnostics
