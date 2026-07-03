from __future__ import annotations

import re

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FileSystem


def check_match_content(
    *,
    expected: list[str],
    context: PredicateContext,
    file_system: FileSystem,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that the file's content matches each expected regex pattern."""
    source = file_system.read_file(context.path)
    diagnostics: list[Diagnostic] = []

    for pattern in expected:
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as error:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="matchContent",
                    message=f'Invalid regex "{pattern}": {error}',
                    convention_name=convention_name,
                    severity=severity,
                    expected=pattern,
                    found=str(error),
                    fix_hint=f'Fix the invalid regex pattern "{pattern}": {error}.',
                )
            )
            continue

        if regex.search(source) is not None:
            continue

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="matchContent",
                message=f'File content must match regex "{pattern}"',
                convention_name=convention_name,
                severity=severity,
                expected=pattern,
                fix_hint=f"Add content to {context.path} that matches the pattern `{pattern}`.",
            )
        )

    return diagnostics
