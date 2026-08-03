from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Literal

from konpy.python_ast._collector import _Collector, _ImportBinding, _position
from konpy.python_ast._dotted import _join_from_and_source, _written_and_resolved
from konpy.python_ast._imports import (
    _is_type_checking_test,
    _TypingAliases,
    _written_from_specifier,
)
from konpy.python_ast.structure import (
    BaseClassRefInfo,
    CallSiteInfo,
    DecoratorInfo,
    ScopedImportInfo,
)

_Scope = Literal["module", "class", "function"]


@dataclass
class _WalkState:
    collector: _Collector
    bindings: dict[str, _ImportBinding]
    aliases: _TypingAliases
    qualified_parts: list[str] = field(default_factory=list)
    scope_stack: list[Literal["class", "function"]] = field(default_factory=list)
    in_type_checking: bool = False


def _call_scope(state: _WalkState) -> _Scope:
    return state.scope_stack[-1] if state.scope_stack else "module"


def _import_scope(state: _WalkState) -> Literal["module", "function"]:
    return (
        "function"
        if state.scope_stack and state.scope_stack[-1] == "function"
        else "module"
    )


def _visit_node(node: ast.AST, state: _WalkState) -> None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        _visit_def(node, state)
    elif isinstance(node, ast.ClassDef):
        _visit_class(node, state)
    elif isinstance(node, ast.Call):
        _visit_call(node, state)
    elif isinstance(node, ast.If):
        _visit_if(node, state)
    elif isinstance(node, ast.Import):
        _visit_import(node, state)
    elif isinstance(node, ast.ImportFrom):
        _visit_import_from(node, state)
    else:
        _visit_children(node, state)


def _visit_children(node: ast.AST, state: _WalkState) -> None:
    for child in ast.iter_child_nodes(node):
        _visit_node(child, state)


def _visit_def(node: ast.FunctionDef | ast.AsyncFunctionDef, state: _WalkState) -> None:
    qualified_name = ".".join((*state.qualified_parts, node.name))
    _collect_decorators(
        node, state, target_kind="function", target_qualified_name=qualified_name
    )
    for decorator in node.decorator_list:
        _visit_node(decorator, state)
    _visit_node(node.args, state)
    if node.returns is not None:
        _visit_node(node.returns, state)

    state.qualified_parts.append(node.name)
    state.scope_stack.append("function")
    for stmt in node.body:
        _visit_node(stmt, state)
    state.scope_stack.pop()
    state.qualified_parts.pop()


def _visit_class(node: ast.ClassDef, state: _WalkState) -> None:
    qualified_name = ".".join((*state.qualified_parts, node.name))
    _collect_decorators(
        node, state, target_kind="class", target_qualified_name=qualified_name
    )
    _collect_bases(node, state, class_qualified_name=qualified_name)
    for decorator in node.decorator_list:
        _visit_node(decorator, state)
    for base in node.bases:
        _visit_node(base, state)
    for keyword in node.keywords:
        _visit_node(keyword, state)

    state.qualified_parts.append(node.name)
    state.scope_stack.append("class")
    for stmt in node.body:
        _visit_node(stmt, state)
    state.scope_stack.pop()
    state.qualified_parts.pop()


def _visit_call(node: ast.Call, state: _WalkState) -> None:
    result = _written_and_resolved(node.func, state.bindings)
    if result is not None:
        written, resolved = result
        state.collector.call_sites.append(
            CallSiteInfo(
                written=written,
                resolved=resolved,
                pos=_position(node),
                scope=_call_scope(state),
            )
        )
    _visit_children(node, state)


def _visit_if(node: ast.If, state: _WalkState) -> None:
    if not _is_type_checking_test(node.test, state.aliases):
        _visit_children(node, state)
        return

    previous = state.in_type_checking
    state.in_type_checking = True
    for stmt in node.body:
        _visit_node(stmt, state)

    state.in_type_checking = False
    for stmt in node.orelse:
        _visit_node(stmt, state)

    state.in_type_checking = previous


def _visit_import(node: ast.Import, state: _WalkState) -> None:
    scope = _import_scope(state)
    is_type = scope == "module" and state.in_type_checking
    pos = _position(node)
    for alias in node.names:
        state.collector.scoped_imports.append(
            ScopedImportInfo(
                source=alias.name,
                symbol_path=alias.name,
                pos=pos,
                scope=scope,
                is_type=is_type,
            )
        )


def _visit_import_from(node: ast.ImportFrom, state: _WalkState) -> None:
    scope = _import_scope(state)
    is_type = scope == "module" and state.in_type_checking
    from_ = _written_from_specifier(module=node.module, level=node.level)
    pos = _position(node)
    for alias in node.names:
        state.collector.scoped_imports.append(
            ScopedImportInfo(
                source=from_,
                symbol_path=_join_from_and_source(from_, alias.name),
                pos=pos,
                scope=scope,
                is_type=is_type,
            )
        )


def _collect_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    state: _WalkState,
    *,
    target_kind: Literal["function", "class"],
    target_qualified_name: str,
) -> None:
    for decorator in node.decorator_list:
        is_call = isinstance(decorator, ast.Call)
        expr = decorator.func if is_call else decorator
        result = _written_and_resolved(expr, state.bindings)
        if result is None:
            continue
        written, resolved = result
        state.collector.decorators.append(
            DecoratorInfo(
                written=written,
                resolved=resolved,
                pos=_position(decorator),
                target_kind=target_kind,
                target_qualified_name=target_qualified_name,
                is_call=is_call,
            )
        )


def _collect_bases(
    node: ast.ClassDef, state: _WalkState, *, class_qualified_name: str
) -> None:
    for base in node.bases:
        expr = base.value if isinstance(base, ast.Subscript) else base
        result = _written_and_resolved(expr, state.bindings)
        if result is None:
            continue
        written, resolved = result
        state.collector.base_class_refs.append(
            BaseClassRefInfo(
                written=written,
                resolved=resolved,
                pos=_position(base),
                class_qualified_name=class_qualified_name,
            )
        )


def _collect_dotted_refs(
    module: ast.Module,
    collector: _Collector,
    aliases: _TypingAliases,
) -> None:
    state = _WalkState(
        collector=collector, bindings=collector.import_bindings, aliases=aliases
    )
    _visit_node(module, state)


__all__: list[str] = []
