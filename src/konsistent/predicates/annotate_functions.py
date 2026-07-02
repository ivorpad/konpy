from __future__ import annotations

from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import get_value
from konsistent.python_ast.structure import PyFileStructure


def _option_enabled(expected: Any, key: str, *, default: bool) -> bool:
    if expected is True:
        return default

    value = get_value(expected, key)
    return default if value is None else bool(value)


def check_annotate_functions(
    *,
    expected: Any,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    check_returns = _option_enabled(expected, "returns", default=True)
    check_params = _option_enabled(expected, "params", default=True)
    public_only = _option_enabled(expected, "publicOnly", default=True)

    diagnostics: list[Diagnostic] = []

    for function in structure.function_annotation_targets:
        if public_only and not function.is_public:
            continue

        if check_params:
            for param in function.params:
                if param.type_name is not None:
                    continue
                diagnostics.append(
                    create_diagnostic(
                        file_path=context.path,
                        predicate_name="annotateFunctions",
                        message=(
                            f'Function "{function.qualified_name}" parameter '
                            f'"{param.name}" must have a type annotation'
                        ),
                        convention_name=convention_name,
                        line=function.pos.line,
                        column=function.pos.column,
                        severity=severity,
                        expected=f'type annotation for parameter "{param.name}"',
                        fix_hint=(
                            f'Annotate parameter "{param.name}" in function '
                            f'"{function.qualified_name}", e.g. `{param.name}: <Type>`.'
                        ),
                    )
                )

        if check_returns and function.return_type is None:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="annotateFunctions",
                    message=(
                        f'Function "{function.qualified_name}" must have a '
                        "return type annotation"
                    ),
                    convention_name=convention_name,
                    line=function.pos.line,
                    column=function.pos.column,
                    severity=severity,
                    expected="return type annotation",
                    fix_hint=(
                        f'Add a return type annotation to function '
                        f'"{function.qualified_name}", e.g. `-> <Type>:`.'
                    ),
                )
            )

    return diagnostics
