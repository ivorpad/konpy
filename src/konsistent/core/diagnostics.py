from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DiagnosticSeverity = Literal["error", "warning"]


@dataclass(frozen=True, kw_only=True)
class Diagnostic:
    file_path: str
    predicate_name: str
    message: str
    severity: DiagnosticSeverity = "error"
    convention_name: str | None = None
    line: int | None = None
    column: int | None = None
    description: str | None = None
    hint: str | None = None
    expected: str | None = None
    found: str | None = None
    fix_hint: str | None = None


def create_diagnostic(
    *,
    file_path: str,
    predicate_name: str,
    message: str,
    convention_name: str | None = None,
    line: int | None = None,
    column: int | None = None,
    severity: DiagnosticSeverity | None = None,
    description: str | None = None,
    hint: str | None = None,
    expected: str | None = None,
    found: str | None = None,
    fix_hint: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name=predicate_name,
        message=message,
        convention_name=convention_name,
        line=line,
        column=column,
        severity=severity or "error",
        description=description,
        hint=hint,
        expected=expected,
        found=found,
        fix_hint=fix_hint,
    )


__all__ = ["Diagnostic", "DiagnosticSeverity", "create_diagnostic"]
