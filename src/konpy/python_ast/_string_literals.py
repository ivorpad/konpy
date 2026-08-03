from __future__ import annotations

import ast

from konpy.python_ast._annotations import _is_type_alias_annotation
from konpy.python_ast._collector import _Collector, _position
from konpy.python_ast._dunder_all import _is_all_statement
from konpy.python_ast.structure import StringLiteralInfo


def _collect_string_literals(module: ast.Module, collector: _Collector) -> None:
    excluded_node_ids = _excluded_string_literal_node_ids(module)
    parent_map = _parent_map(module)
    literals: list[StringLiteralInfo] = []

    for node in ast.walk(module):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value == "":
            continue
        if id(node) in excluded_node_ids:
            continue
        if _is_bare_string_expression(node, parent_map):
            continue
        if _has_joined_string_ancestor(node, parent_map):
            continue

        literals.append(
            StringLiteralInfo(
                value=node.value,
                pos=_position(node),
                is_mapping_key=_is_mapping_key(node, parent_map),
            )
        )

    collector.string_literals.extend(
        sorted(literals, key=lambda item: (item.pos.line, item.pos.column, item.value))
    )


def _parent_map(root: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(root):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _excluded_string_literal_node_ids(module: ast.Module) -> set[int]:
    excluded: set[int] = set()

    for node in ast.walk(module):
        if isinstance(node, ast.stmt) and _is_all_statement(node):
            excluded.update(_descendant_ids(node))
            continue

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _add_function_annotation_ids(node, excluded)
            _add_type_param_ids(node, excluded)

        if isinstance(node, ast.ClassDef):
            _add_type_param_ids(node, excluded)

        if isinstance(node, ast.AnnAssign):
            excluded.update(_descendant_ids(node.annotation))
            if _is_type_alias_annotation(node.annotation) and node.value is not None:
                excluded.update(_descendant_ids(node.value))

        if isinstance(node, ast.TypeAlias):
            excluded.update(_descendant_ids(node.value))
            _add_type_param_ids(node, excluded)

        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            value = _dunder_sequence_assignment_value(node)
            if value is not None:
                excluded.update(_string_literal_ids(value))

        if isinstance(node, ast.Compare) and _compare_mentions_dunder_name(node):
            excluded.update(_string_literal_ids(node))

    return excluded


def _add_function_annotation_ids(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    excluded: set[int],
) -> None:
    arguments = [
        *node.args.posonlyargs,
        *node.args.args,
        *node.args.kwonlyargs,
    ]
    if node.args.vararg is not None:
        arguments.append(node.args.vararg)
    if node.args.kwarg is not None:
        arguments.append(node.args.kwarg)

    for argument in arguments:
        if argument.annotation is not None:
            excluded.update(_descendant_ids(argument.annotation))

    if node.returns is not None:
        excluded.update(_descendant_ids(node.returns))


def _add_type_param_ids(node: ast.AST, excluded: set[int]) -> None:
    for type_param in _type_params(node):
        excluded.update(_descendant_ids(type_param))


def _type_params(node: ast.AST) -> tuple[ast.AST, ...]:
    raw = getattr(node, "type_params", ())
    return tuple(item for item in raw if isinstance(item, ast.AST))


def _descendant_ids(node: ast.AST) -> set[int]:
    return {id(descendant) for descendant in ast.walk(node)}


def _string_literal_ids(node: ast.AST) -> set[int]:
    return {
        id(descendant)
        for descendant in ast.walk(node)
        if isinstance(descendant, ast.Constant) and isinstance(descendant.value, str)
    }


def _is_bare_string_expression(
    node: ast.Constant,
    parent_map: dict[ast.AST, ast.AST],
) -> bool:
    parent = parent_map.get(node)
    return isinstance(parent, ast.Expr) and parent.value is node


_MAPPING_ACCESSORS = frozenset({"get", "pop", "setdefault"})


def _is_mapping_key(node: ast.Constant, parent_map: dict[ast.AST, ast.AST]) -> bool:
    """Literal used as a mapping key: dict-display key, subscript index, or
    the key argument of a `.get()`-style accessor."""
    parent = parent_map.get(node)
    if isinstance(parent, ast.Dict):
        return any(key is node for key in parent.keys)
    if isinstance(parent, ast.Subscript):
        return parent.slice is node
    if isinstance(parent, ast.Call) and isinstance(node.value, str):
        return (
            isinstance(parent.func, ast.Attribute)
            and parent.func.attr in _MAPPING_ACCESSORS
            and bool(parent.args)
            and parent.args[0] is node
            # Any receiver has a `.get` — requests.get("https://…") passes a
            # URL, not a key. Keys have no whitespace and no scheme.
            and "://" not in node.value
            and not any(char.isspace() for char in node.value)
        )
    return False


def _has_joined_string_ancestor(
    node: ast.AST,
    parent_map: dict[ast.AST, ast.AST],
) -> bool:
    current = parent_map.get(node)
    while current is not None:
        if isinstance(current, ast.JoinedStr):
            return True
        current = parent_map.get(current)
    return False


def _dunder_sequence_assignment_value(
    node: ast.Assign | ast.AnnAssign | ast.AugAssign,
) -> ast.expr | None:
    value: ast.expr | None = None

    if isinstance(node, ast.Assign):
        if not any(_is_dunder_target(target) for target in node.targets):
            return None
        value = node.value
    elif isinstance(node, ast.AnnAssign):
        if not _is_dunder_target(node.target):
            return None
        value = node.value
    elif _is_dunder_target(node.target):
        value = node.value

    if isinstance(value, ast.List | ast.Tuple | ast.Set):
        return value
    return None


def _is_dunder_target(target: ast.AST) -> bool:
    return (
        isinstance(target, ast.Name)
        and target.id.startswith("__")
        and target.id.endswith("__")
    )


def _compare_mentions_dunder_name(node: ast.Compare) -> bool:
    operands: list[ast.expr] = [node.left, *node.comparators]
    return any(
        isinstance(operand, ast.Name) and operand.id == "__name__"
        for operand in operands
    )


__all__: list[str] = []
