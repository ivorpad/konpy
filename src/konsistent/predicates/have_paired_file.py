from __future__ import annotations

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FileSystem


def check_have_paired_file(
    *,
    expected: str,
    context: PredicateContext,
    file_system: FileSystem,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that the expected paired file template resolves to an existing file."""
    resolved = context.resolve_template(expected)
    if file_system.file_exists(resolved):
        return []

    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="havePairedFile",
            message=f"Missing paired file: {resolved}",
            convention_name=convention_name,
            severity=severity,
            expected=resolved,
            fix_hint=f'Create the paired file at "{resolved}".',
        )
    ]
