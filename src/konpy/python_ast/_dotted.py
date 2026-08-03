from __future__ import annotations

import ast

from konpy.python_ast._collector import _ImportBinding


def _dotted_parts(expr: ast.expr) -> tuple[str, ...] | None:
    parts: list[str] = []
    node = expr
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if not isinstance(node, ast.Name):
        return None

    parts.append(node.id)
    parts.reverse()
    return tuple(parts)


def _join_from_and_source(from_: str, source_name: str) -> str:
    if not from_:
        return source_name
    if from_.endswith("."):
        return f"{from_}{source_name}"
    return f"{from_}.{source_name}"


def _resolve_dotted(
    parts: tuple[str, ...],
    bindings: dict[str, _ImportBinding],
) -> str:
    root = parts[0]
    binding = bindings.get(root)
    if binding is None:
        return ".".join(parts)

    resolved_root = (
        binding.source_name
        if binding.is_module_import
        else _join_from_and_source(binding.from_, binding.source_name)
    )
    return ".".join((resolved_root, *parts[1:]))


def _written_and_resolved(
    expr: ast.expr,
    bindings: dict[str, _ImportBinding],
) -> tuple[str, str] | None:
    parts = _dotted_parts(expr)
    if parts is None:
        return None
    return ".".join(parts), _resolve_dotted(parts, bindings)


__all__: list[str] = []
