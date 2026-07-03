from __future__ import annotations

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic


def check_have_files(
    *,
    expected: list[str],
    context: PredicateContext,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that each expected file template resolves to an existing file."""
    diagnostics: list[Diagnostic] = []
    for file_template in expected:
        resolved = context.resolve_template(file_template)
        if context.file_exists(resolved):
            continue
        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="haveFiles",
                message=f"Missing required file: {resolved}",
                convention_name=convention_name,
                severity=severity,
            )
        )
    return diagnostics
