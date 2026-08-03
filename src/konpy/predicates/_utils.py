from __future__ import annotations

from collections.abc import Mapping

from konpy.config.schema import (
    ClassDefinitionV1,
    DeclarationDefinitionV1,
    ExportDefinitionV1,
    FunctionDefinitionV1,
    ImportDefinitionV1,
    InterfaceDefinitionV1,
)
from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.python_ast.structure import FunctionInfo, TypeAnnotationInfo

DefinitionEntry = (
    str
    | dict[str, str]
    | ExportDefinitionV1
    | ImportDefinitionV1
    | DeclarationDefinitionV1
    | FunctionDefinitionV1
    | InterfaceDefinitionV1
    | ClassDefinitionV1
)


def get_value(obj: object, key: str, default: object = None) -> object:
    """Read `key` from a mapping or attribute-style object, falling back to `default`."""
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_from_value(obj: object) -> str | None:
    """Return a definition entry's `from`/`from_` source, if any."""
    value = get_value(obj, "from_", None)
    if value is None:
        value = get_value(obj, "from", None)
    return value if isinstance(value, str) else None


def definition_name(entry: DefinitionEntry, context: PredicateContext) -> str:
    """Resolve a definition entry (string or object) to its templated name."""
    if isinstance(entry, str):
        return context.resolve_template(entry)
    return context.resolve_template(str(get_value(entry, "name", "")))


def definition_from(entry: DefinitionEntry, context: PredicateContext) -> str | None:
    """Resolve a definition entry's templated `from` source, if any."""
    value = get_from_value(entry)
    if not isinstance(value, str):
        return None
    return context.resolve_template(value)


def resolve_extend_type(extend: object, context: PredicateContext) -> str | None:
    """Resolve an `extend` clause (string or object) to its templated type name."""
    if extend is None:
        return None
    if isinstance(extend, str):
        return context.resolve_template(extend)
    return context.resolve_template(str(get_value(extend, "type", "")))


def resolve_implement_types(implement: object, context: PredicateContext) -> list[str]:
    """Resolve an `implement` list to its templated type names."""
    if not isinstance(implement, list):
        return []
    values: list[str] = []
    for entry in implement:
        resolved = resolve_extend_type(entry, context)
        if resolved:
            values.append(resolved)
    return values


def type_matches(actual: TypeAnnotationInfo | None, expected: str) -> bool:
    """Check whether a resolved type annotation matches the expected type name."""
    return actual is not None and (actual.text == expected or actual.base_name == expected)


def check_function_signature(
    *,
    predicate_name: str,
    function_info: FunctionInfo,
    definition: dict[str, str] | FunctionDefinitionV1,
    resolved_name: str,
    context: PredicateContext,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check a function's parameter and return type annotations against a definition."""
    diagnostics: list[Diagnostic] = []
    receive_param = get_value(definition, "receiveParamOfType")
    receive_params = get_value(definition, "receiveParamsOfTypes")
    return_type = get_value(definition, "returnValueOfType")

    resolved_param = None
    if isinstance(receive_param, str):
        resolved_param = context.resolve_template(receive_param)

    resolved_params = None
    if isinstance(receive_params, list) and receive_params:
        resolved_params = [
            context.resolve_template(item) for item in receive_params if isinstance(item, str)
        ]

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
