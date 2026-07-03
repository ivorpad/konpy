from __future__ import annotations

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.python_ast.structure import PyFileStructure

_MESSAGES = {
    "declaration": "Barrel file must not contain declarations",
    "expression": "Barrel file must not contain top-level expression statements",
}


def check_are_barrel_files(
    *,
    expected: bool,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that a barrel file contains only re-export statements, no declarations."""
    if not expected:
        return []

    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="areBarrelFiles",
            message=_MESSAGES[entry.kind],
            convention_name=convention_name,
            line=entry.pos.line,
            column=entry.pos.column,
            severity=severity,
        )
        for entry in structure.non_barrel_statements
    ]
