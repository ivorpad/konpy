from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.python_ast.structure import FunctionInfo, TypeAnnotationInfo


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_from_value(obj: Any) -> str | None:
    value = get_value(obj, "from_", None)
    if value is None:
        value = get_value(obj, "from", None)
    return value


def definition_name(entry: Any, context: PredicateContext) -> str:
    if isinstance(entry, str):
        return context.resolve_template(entry)
    return context.resolve_template(str(get_value(entry, "name", "")))


def definition_from(entry: Any, context: PredicateContext) -> str | None:
    value = get_from_value(entry)
    if not isinstance(value, str):
        return None
    return context.resolve_template(value)


def resolve_extend_type(extend: Any, context: PredicateContext) -> str | None:
    if extend is None:
        return None
    if isinstance(extend, str):
        return context.resolve_template(extend)
    return context.resolve_template(str(get_value(extend, "type", "")))


def resolve_implement_types(implement: list[Any] | None, context: PredicateContext) -> list[str]:
    if implement is None:
        return []
    values: list[str] = []
    for entry in implement:
        resolved = resolve_extend_type(entry, context)
        if resolved:
            values.append(resolved)
    return values


def type_matches(actual: TypeAnnotationInfo | None, expected: str) -> bool:
    return actual is not None and (actual.text == expected or actual.base_name == expected)


def check_function_signature(
    *,
    predicate_name: str,
    function_info: FunctionInfo,
    definition: Any,
    resolved_name: str,
    context: PredicateContext,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    receive_param = get_value(definition, "receiveParamOfType")
    receive_params = get_value(definition, "receiveParamsOfTypes")
    return_type = get_value(definition, "returnValueOfType")

    resolved_param = None
    if isinstance(receive_param, str):
        resolved_param = context.resolve_template(receive_param)

    resolved_params = None
    if receive_params:
        resolved_params = [context.resolve_template(item) for item in receive_params]

    resolved_return = None
    if isinstance(return_type, str):
        resolved_return = context.resolve_template(return_type)

    if resolved_param:
        has_param = any(
            type_matches(param.type_name, resolved_param)
            for param in function_info.params
        )
        if not has_param:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name=predicate_name,
                    message=(
                        f'Function "{resolved_name}" must receive a parameter '
                        f'of type "{resolved_param}"'
                    ),
                    convention_name=convention_name,
                    line=function_info.pos.line,
                    column=function_info.pos.column,
                    severity=severity,
                )
            )

    if resolved_params is not None:
        for index, expected_type in enumerate(resolved_params):
            actual = None
            if index < len(function_info.params):
                actual = function_info.params[index].type_name
            if type_matches(actual, expected_type):
                continue
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name=predicate_name,
                    message=(
                        f'Function "{resolved_name}" parameter {index + 1} '
                        f'must be of type "{expected_type}"'
                    ),
                    convention_name=convention_name,
                    line=function_info.pos.line,
                    column=function_info.pos.column,
                    severity=severity,
                )
            )

    if resolved_return and not type_matches(function_info.return_type, resolved_return):
        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name=predicate_name,
                message=(
                    f'Function "{resolved_name}" must return value '
                    f'of type "{resolved_return}"'
                ),
                convention_name=convention_name,
                line=function_info.pos.line,
                column=function_info.pos.column,
                severity=severity,
            )
        )

    return diagnostics
