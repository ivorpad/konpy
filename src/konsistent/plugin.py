from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.python_ast.structure import PyFileStructure


class PluginPredicateHandler(Protocol):
    """Callable signature a plugin implements to evaluate its predicate."""

    def __call__(
        self,
        *,
        expected: object,
        context: PredicateContext,
        structure: PyFileStructure | None,
        convention_name: str | None = None,
        severity: DiagnosticSeverity | None = None,
    ) -> list[Diagnostic]: ...


class PluginForbiddenMessageBuilder(Protocol):
    """Callable signature a plugin implements to build a must-not violation message."""

    def __call__(
        self,
        *,
        expected: object,
        context: PredicateContext,
    ) -> str: ...


@dataclass(frozen=True, kw_only=True)
class PredicatePlugin:
    """Registration record for a third-party predicate: its config model, handler, and message."""

    key: str
    value_model: object
    handler: PluginPredicateHandler
    forbidden_message_template: str | PluginForbiddenMessageBuilder
    uses_ast: bool = False
    item_level_must_not: bool = False
    validate_placeholders: bool = True


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
    "PluginForbiddenMessageBuilder",
    "PluginPredicateHandler",
    "PredicateContext",
    "PredicatePlugin",
    "PyFileStructure",
    "create_diagnostic",
]
