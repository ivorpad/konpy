from __future__ import annotations

from typing import Literal

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FileSystem


def check_have_type(
    *,
    expected: Literal["file", "directory"],
    context: PredicateContext,
    file_system: FileSystem,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    is_dir = file_system.is_directory(context.path)
    exists = file_system.file_exists(context.path)
    is_file = exists and not is_dir

    if expected == "file" and not is_file:
        message = (
            "Expected a file but found a directory"
            if is_dir
            else "Expected a file but path does not exist"
        )
        return [
            create_diagnostic(
                file_path=context.path,
                predicate_name="haveType",
                message=message,
                convention_name=convention_name,
                severity=severity,
            )
        ]

    if expected == "directory" and not is_dir:
        message = (
            "Expected a directory but found a file"
            if is_file
            else "Expected a directory but path does not exist"
        )
        return [
            create_diagnostic(
                file_path=context.path,
                predicate_name="haveType",
                message=message,
                convention_name=convention_name,
                severity=severity,
            )
        ]

    return []
