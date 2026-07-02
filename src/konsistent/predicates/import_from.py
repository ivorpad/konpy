from __future__ import annotations

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.python_ast.structure import PyFileStructure


def _matches_source(*, source: str, expected: str) -> bool:
    if source == expected:
        return True
    if expected.startswith("."):
        return False
    return source.startswith(f"{expected}.")


def check_import_from(
    *,
    expected: str,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    resolved = context.resolve_template(expected)
    found = any(
        _matches_source(source=source.from_, expected=resolved)
        for source in structure.import_sources
    )
    if found:
        return []

    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="importFrom",
            message=f'Missing import from "{resolved}"',
            convention_name=convention_name,
            severity=severity,
        )
    ]
