from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

type _Normalized = bool | int | float | str | None | tuple[object, ...]

_IGNORED_FIELD_NAMES = {
    "annotation",
    "ctx",
    "decorator_list",
    "returns",
    "type_comment",
    "type_params",
}


@dataclass(frozen=True, kw_only=True)
class _FingerprintResult:
    fingerprint: str
    statement_count: int


def _fingerprint_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> _FingerprintResult:
    normalizer = _NameNormalizer()
    normalizer.bind_parameters(node.args)

    normalized = normalizer.normalize_function(node)
    serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return _FingerprintResult(
        fingerprint=fingerprint,
        statement_count=_function_statement_count(node),
    )


class _NameNormalizer:
    def __init__(self) -> None:
        self._bindings: dict[str, str] = {}

    def bind_parameters(self, args: ast.arguments) -> None:
        for argument in [*args.posonlyargs, *args.args]:
            self._bind(argument.arg)
        if args.vararg is not None:
            self._bind(args.vararg.arg)
        for argument in args.kwonlyargs:
            self._bind(argument.arg)
        if args.kwarg is not None:
            self._bind(args.kwarg.arg)

    def normalize_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> _Normalized:
        return (
            "Function",
            ("async", isinstance(node, ast.AsyncFunctionDef)),
            ("arguments", self._argument_shape(node.args)),
            ("body", self._normalize_sequence(_body_without_docstring(node.body))),
        )

    def _normalize_value(self, value: object) -> _Normalized:
        if isinstance(value, ast.AST):
            return self._normalize_node(value)
        if isinstance(value, list | tuple):
            return tuple(self._normalize_value(item) for item in value)
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return repr(value)

    def _normalize_node(self, node: ast.AST) -> _Normalized:
        if isinstance(node, ast.Name):
            return self._normalize_name(node)
        if isinstance(node, ast.Constant):
            return self._normalize_constant(node)
        if isinstance(node, ast.arg):
            return ("arg",)
        if isinstance(node, ast.Lambda):
            return self._normalize_lambda(node)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            return self._normalize_nested_function(node)
        if isinstance(node, ast.ClassDef):
            return self._normalize_nested_class(node)

        fields: list[_Normalized] = []
        for field_name, value in ast.iter_fields(node):
            if field_name in _IGNORED_FIELD_NAMES:
                continue
            fields.append((field_name, self._normalize_value(value)))

        return (type(node).__name__, tuple(fields))

    def _normalize_name(self, node: ast.Name) -> _Normalized:
        if isinstance(node.ctx, ast.Store | ast.Del):
            return ("local", self._bind(node.id), type(node.ctx).__name__)
        if node.id in self._bindings:
            return ("local", self._bindings[node.id], "Load")
        return ("free", node.id, "Load")

    def _normalize_constant(self, node: ast.Constant) -> _Normalized:
        return ("Constant", type(node.value).__name__, repr(node.value))

    def _normalize_nested_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> _Normalized:
        name_token = self._bind(node.name)
        self.bind_parameters(node.args)

        return (
            "NestedFunction",
            name_token,
            ("async", isinstance(node, ast.AsyncFunctionDef)),
            ("arguments", self._argument_shape(node.args)),
            ("body", self._normalize_sequence(_body_without_docstring(node.body))),
        )

    def _normalize_lambda(self, node: ast.Lambda) -> _Normalized:
        self.bind_parameters(node.args)

        return (
            "Lambda",
            ("arguments", self._argument_shape(node.args)),
            ("body", self._normalize_node(node.body)),
        )

    def _normalize_nested_class(self, node: ast.ClassDef) -> _Normalized:
        return (
            "NestedClass",
            self._bind(node.name),
            ("bases", self._normalize_sequence(node.bases)),
            ("keywords", self._normalize_sequence(node.keywords)),
            ("body", self._normalize_sequence(node.body)),
        )

    def _argument_shape(self, args: ast.arguments) -> _Normalized:
        positional = [*args.posonlyargs, *args.args]
        defaults = _align_positional_defaults(
            positional_count=len(positional),
            defaults=args.defaults,
        )

        return (
            "arguments",
            ("posonly", len(args.posonlyargs)),
            ("positional", len(args.args)),
            ("vararg", args.vararg is not None),
            ("kwonly", len(args.kwonlyargs)),
            ("kwarg", args.kwarg is not None),
            (
                "positional_defaults",
                tuple(self._normalize_default(default) for default in defaults),
            ),
            (
                "keyword_defaults",
                tuple(self._normalize_default(default) for default in args.kw_defaults),
            ),
        )

    def _normalize_default(self, node: ast.expr | None) -> _Normalized:
        if node is None:
            return ("no-default",)
        return ("default", self._normalize_node(node))

    def _normalize_sequence(self, values: Sequence[ast.AST]) -> _Normalized:
        return tuple(self._normalize_node(value) for value in values)

    def _bind(self, name: str) -> str:
        existing = self._bindings.get(name)
        if existing is not None:
            return existing

        token = f"$v{len(self._bindings)}"
        self._bindings[name] = token
        return token


def _align_positional_defaults(
    *,
    positional_count: int,
    defaults: list[ast.expr],
) -> tuple[ast.expr | None, ...]:
    missing = positional_count - len(defaults)
    return (*((None,) * missing), *defaults)


def _body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if body and _is_string_expression_statement(body[0]):
        return body[1:]
    return body


def _function_statement_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return sum(_statement_count(statement) for statement in _body_without_docstring(node.body))


def _statement_count(statement: ast.stmt) -> int:
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return 1
    return 1 + _child_statement_count(statement)


def _child_statement_count(node: ast.AST) -> int:
    total = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            total += 1
        elif isinstance(child, ast.stmt):
            total += _statement_count(child)
        else:
            total += _child_statement_count(child)
    return total


def _is_string_expression_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


__all__: list[str] = []
