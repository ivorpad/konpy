from __future__ import annotations

from dataclasses import dataclass

from konpy.config.schema import DeclarationDefinitionV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import definition_name
from konpy.python_ast.structure import (
    DeclarationSymbolInfo,
    DeclarationSymbolKind,
    PyFileStructure,
)


@dataclass(frozen=True, kw_only=True)
class DeclarationCheckContext:
    """Shared parameters for reporting declare-* declaration diagnostics."""

    context: PredicateContext
    predicate_name: str
    convention_name: str | None = None
    severity: DiagnosticSeverity | None = None


def resolve_definition_name(
    *, entry: str | DeclarationDefinitionV1, context: PredicateContext
) -> str:
    """Resolve a declaration entry (string or object) to its templated name."""
    return definition_name(entry, context)


def find_declaration_symbol(
    *,
    structure: PyFileStructure,
    kinds: tuple[DeclarationSymbolKind, ...],
    name: str,
) -> DeclarationSymbolInfo | None:
    """Find the local declaration symbol named `name` among the given kinds."""
    return next(
        (
            symbol
            for symbol in structure.declaration_symbols
            if symbol.name == name and symbol.kind in kinds
        ),
        None,
    )


def is_declaration_symbol_exported(
    *,
    structure: PyFileStructure,
    symbol: DeclarationSymbolInfo,
) -> bool:
    """Check whether a local declaration symbol is exported from the module."""
    return (
        symbol.is_exported
        or symbol.is_default_export
        or any(item.source_name == symbol.name for item in structure.named_export_symbols)
        or any(item.name == symbol.name for item in structure.default_export_symbols)
    )


def create_missing_declaration_diagnostic(
    *,
    check_context: DeclarationCheckContext,
    label: str,
    name: str,
) -> Diagnostic:
    """Build a diagnostic for a missing local declaration."""
    return create_diagnostic(
        file_path=check_context.context.path,
        predicate_name=check_context.predicate_name,
        message=f'Missing local {label} declaration "{name}"',
        convention_name=check_context.convention_name,
        severity=check_context.severity,
    )


def create_exported_declaration_diagnostic(
    *,
    check_context: DeclarationCheckContext,
    label: str,
    symbol: DeclarationSymbolInfo,
) -> Diagnostic:
    """Build a diagnostic for a local declaration that must not be exported."""
    return create_diagnostic(
        file_path=check_context.context.path,
        predicate_name=check_context.predicate_name,
        message=f'Local {label} declaration "{symbol.name}" must not be exported',
        convention_name=check_context.convention_name,
        line=symbol.pos.line,
        column=symbol.pos.column,
        severity=check_context.severity,
    )
