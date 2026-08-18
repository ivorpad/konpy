from __future__ import annotations

from typing import Literal

from konpy.config.schema import AnnotateFunctionsOptionsV1
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import option_bool
from konpy.python_ast.structure import PyFileStructure


def check_annotate_functions(
    *,
    expected: Literal[True] | AnnotateFunctionsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that public functions annotate their parameters and/or return type."""
    check_returns = option_bool(expected, "returns", default=True)
    check_params = option_bool(expected, "params", default=True)
    public_only = option_bool(expected, "publicOnly", default=True)

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
                        f'Function "{function.qualified_name}" must have a return type annotation'
                    ),
                    convention_name=convention_name,
                    line=function.pos.line,
                    column=function.pos.column,
                    severity=severity,
                    expected="return type annotation",
                    fix_hint=(
                        f"Add a return type annotation to function "
                        f'"{function.qualified_name}", e.g. `-> <Type>:`.'
                    ),
                )
            )

    return diagnostics
