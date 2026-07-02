from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import (
    definition_name,
    get_value,
    resolve_extend_type,
    resolve_implement_types,
)
from konsistent.python_ast.structure import PyFileStructure


def check_export_classes(
    *,
    expected: list[Any],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for entry in expected:
        definition = {"name": entry} if isinstance(entry, str) else entry
        name = definition_name(definition, context)
        is_exported = any(
            export.name == name and export.kind in {"class", "re-export"}
            for export in structure.exports
        )
        class_info = next((cls for cls in structure.classes if cls.name == name), None)

        if not is_exported:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="exportClasses",
                    message=f'Missing export class "{name}"',
                    convention_name=convention_name,
                    severity=severity,
                )
            )
            continue

        if class_info is None:
            continue

        expected_extend = resolve_extend_type(get_value(definition, "extend"), context)
        if expected_extend and class_info.extends != expected_extend:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="exportClasses",
                    message=f'Class "{name}" must extend "{expected_extend}"',
                    convention_name=convention_name,
                    line=class_info.pos.line,
                    column=class_info.pos.column,
                    severity=severity,
                )
            )

        for expected_impl in resolve_implement_types(
            get_value(definition, "implement"),
            context,
        ):
            if expected_impl in class_info.implements:
                continue
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="exportClasses",
                    message=f'Class "{name}" must implement "{expected_impl}"',
                    convention_name=convention_name,
                    line=class_info.pos.line,
                    column=class_info.pos.column,
                    severity=severity,
                )
            )

    return diagnostics
