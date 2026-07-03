from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class _AllState:
    names: list[str] | None = None
    is_dynamic: bool = False


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_string_sequence(node: ast.AST | None) -> list[str] | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values: list[str] = []
    for element in node.elts:
        value = _literal_string(element)
        if value is None:
            return None
        values.append(value)
    return values


def _merge_all_names(existing: list[str], incoming: list[str]) -> None:
    for name in incoming:
        if name not in existing:
            existing.append(name)


def _is_all_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _is_all_assign(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return len(node.targets) == 1 and _is_all_name(node.targets[0])
    if isinstance(node, ast.AnnAssign):
        return _is_all_name(node.target)
    return False


def _is_all_augassign(node: ast.stmt) -> bool:
    return isinstance(node, ast.AugAssign) and _is_all_name(node.target)


def _is_all_mutation_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr in {"append", "extend"}
        and _is_all_name(node.value.func.value)
    )


def _is_all_statement(node: ast.stmt) -> bool:
    return _is_all_assign(node) or _is_all_augassign(node) or _is_all_mutation_expr(node)


def _all_statement_literal_values(node: ast.stmt) -> list[str] | None:
    if isinstance(node, ast.Assign) and _is_all_assign(node):
        return _literal_string_sequence(node.value)
    if isinstance(node, ast.AnnAssign) and _is_all_assign(node):
        return _literal_string_sequence(node.value) if node.value is not None else None
    if isinstance(node, ast.AugAssign) and _is_all_augassign(node):
        return _literal_string_sequence(node.value)
    if not _is_all_mutation_expr(node):
        return None

    call = node.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr == "append" and len(call.args) == 1:
        value = _literal_string(call.args[0])
        return [value] if value is not None else None
    if call.func.attr == "extend" and len(call.args) == 1:
        return _literal_string_sequence(call.args[0])
    return None


def _is_allowed_all_statement(node: ast.stmt) -> bool:
    return _is_all_statement(node) and _all_statement_literal_values(node) is not None


def _target_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _is_public(name: str, all_state: _AllState) -> bool:
    if all_state.names is not None:
        return name in all_state.names
    return not name.startswith("_")


def _collect_all_state(body: list[ast.stmt]) -> _AllState:
    state = _AllState()
    for node in body:
        if not _is_all_statement(node):
            continue
        values = _all_statement_literal_values(node)
        if values is None:
            state.names = None
            state.is_dynamic = True
            continue
        if state.is_dynamic:
            continue
        if state.names is None:
            state.names = []
        _merge_all_names(state.names, values)
    return state
