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


def create_diagnostic(
    *,
    file_path: str,
    predicate_name: str,
    message: str,
    convention_name: str | None = None,
    line: int | None = None,
    column: int | None = None,
    severity: DiagnosticSeverity | None = None,
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name=predicate_name,
        message=message,
        convention_name=convention_name,
        line=line,
        column=column,
        severity=severity or "error",
    )


__all__ = ["Diagnostic", "DiagnosticSeverity", "create_diagnostic"]
