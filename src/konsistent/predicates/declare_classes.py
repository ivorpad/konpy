from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import (
    get_value,
    resolve_extend_type,
    resolve_implement_types,
)
from konsistent.predicates.declaration_utils import (
    DeclarationCheckContext,
    create_exported_declaration_diagnostic,
    create_missing_declaration_diagnostic,
    find_declaration_symbol,
    is_declaration_symbol_exported,
)
from konsistent.python_ast.structure import ClassInfo, PyFileStructure


def _check_class_heritage(
    *,
    definition: Any,
    class_info: ClassInfo,
    resolved_name: str,
    context: PredicateContext,
    predicate_name: str,
    convention_name: str | None,
    severity: DiagnosticSeverity | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    expected_extend = resolve_extend_type(get_value(definition, "extend"), context)

    if expected_extend and class_info.extends != expected_extend:
        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name=predicate_name,
                message=f'Class "{resolved_name}" must extend "{expected_extend}"',
                convention_name=convention_name,
                line=class_info.pos.line,
                column=class_info.pos.column,
                severity=severity,
            )
        )

    for expected_impl in resolve_implement_types(get_value(definition, "implement"), context):
        if expected_impl in class_info.implements:
            continue
        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name=predicate_name,
                message=f'Class "{resolved_name}" must implement "{expected_impl}"',
                convention_name=convention_name,
                line=class_info.pos.line,
                column=class_info.pos.column,
                severity=severity,
            )
        )

    return diagnostics


def check_declare_classes(
    *,
    expected: list[Any],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    check_context = DeclarationCheckContext(
        context=context,
        convention_name=convention_name,
        predicate_name="declareClasses",
        severity=severity,
    )

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = context.resolve_template(str(get_value(definition, "name", "")))
        symbol = find_declaration_symbol(
            structure=structure,
            kinds=("class",),
            name=name,
        )
        class_info = next((cls for cls in structure.classes if cls.name == name), None)

        if symbol is None or class_info is None:
            diagnostics.append(
                create_missing_declaration_diagnostic(
                    check_context=check_context,
                    label="class",
                    name=name,
                )
            )
            continue

        if is_declaration_symbol_exported(structure=structure, symbol=symbol):
            diagnostics.append(
                create_exported_declaration_diagnostic(
                    check_context=check_context,
                    label="class",
                    symbol=symbol,
                )
            )
            continue

        diagnostics.extend(
            _check_class_heritage(
                definition=definition,
                class_info=class_info,
                resolved_name=name,
                context=context,
                predicate_name="declareClasses",
                convention_name=convention_name,
                severity=severity,
            )
        )

    return diagnostics
