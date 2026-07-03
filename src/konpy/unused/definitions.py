"""Collect definitions (functions, methods, classes, attributes, constants)
from a parsed ``ast.Module``.

This walks the raw ``ast`` (not ``PyFileStructure``) because unused-code
detection needs more depth than the parity parser exposes: class-body methods
and attributes, per-definition decorators, and owning-class bases/decorators.

Scope (v1): module-level statements and one level of class body. Nested
functions inside functions and local variables are out of scope.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Literal

DefinitionKind = Literal["function", "method", "class", "attribute", "constant"]


@dataclass(frozen=True, kw_only=True)
class Definition:
    """A single collected function/method/class/attribute/constant definition."""

    module_path: str
    name: str
    qualname: str
    kind: DefinitionKind
    decorators: tuple[str, ...]
    class_bases: tuple[str, ...]
    class_decorators: tuple[str, ...]
    lineno: int
    col: int


def collect_definitions(*, module: ast.Module, module_path: str) -> list[Definition]:
    """Collect module-level and one-level-of-class-body definitions from `module`."""
    definitions: list[Definition] = []

    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            definitions.append(
                _make_definition(
                    module_path=module_path,
                    name=node.name,
                    qualname=node.name,
                    kind="function",
                    decorators=_decorator_names(node.decorator_list),
                    class_bases=(),
                    class_decorators=(),
                    node=node,
                )
            )
        elif isinstance(node, ast.ClassDef):
            definitions.append(
                _make_definition(
                    module_path=module_path,
                    name=node.name,
                    qualname=node.name,
                    kind="class",
                    decorators=_decorator_names(node.decorator_list),
                    class_bases=(),
                    class_decorators=(),
                    node=node,
                )
            )
            definitions.extend(_collect_class_members(node=node, module_path=module_path))
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            for target in _name_targets(node):
                definitions.append(
                    _make_definition(
                        module_path=module_path,
                        name=target.id,
                        qualname=target.id,
                        kind="constant",
                        decorators=(),
                        class_bases=(),
                        class_decorators=(),
                        node=target,
                    )
                )

    return definitions


def _collect_class_members(*, node: ast.ClassDef, module_path: str) -> list[Definition]:
    bases = _base_names(node.bases)
    class_decorators = _decorator_names(node.decorator_list)
    members: list[Definition] = []

    for child in node.body:
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            members.append(
                _make_definition(
                    module_path=module_path,
                    name=child.name,
                    qualname=f"{node.name}.{child.name}",
                    kind="method",
                    decorators=_decorator_names(child.decorator_list),
                    class_bases=bases,
                    class_decorators=class_decorators,
                    node=child,
                )
            )
        elif isinstance(child, ast.Assign | ast.AnnAssign):
            for target in _name_targets(child):
                members.append(
                    _make_definition(
                        module_path=module_path,
                        name=target.id,
                        qualname=f"{node.name}.{target.id}",
                        kind="attribute",
                        decorators=(),
                        class_bases=bases,
                        class_decorators=class_decorators,
                        node=target,
                    )
                )

    return members


def _make_definition(
    *,
    module_path: str,
    name: str,
    qualname: str,
    kind: DefinitionKind,
    decorators: tuple[str, ...],
    class_bases: tuple[str, ...],
    class_decorators: tuple[str, ...],
    node: ast.AST,
) -> Definition:
    return Definition(
        module_path=module_path,
        name=name,
        qualname=qualname,
        kind=kind,
        decorators=decorators,
        class_bases=class_bases,
        class_decorators=class_decorators,
        lineno=getattr(node, "lineno", 1),
        col=getattr(node, "col_offset", 0) + 1,
    )


def _name_targets(node: ast.Assign | ast.AnnAssign) -> list[ast.Name]:
    if isinstance(node, ast.AnnAssign):
        return [node.target] if isinstance(node.target, ast.Name) else []
    return [target for target in node.targets if isinstance(target, ast.Name)]


def _decorator_names(decorators: list[ast.expr]) -> tuple[str, ...]:
    return tuple(_decorator_name(decorator) for decorator in decorators)


def _decorator_name(decorator: ast.expr) -> str:
    expr = decorator.func if isinstance(decorator, ast.Call) else decorator
    return ast.unparse(expr)


def _base_names(bases: list[ast.expr]) -> tuple[str, ...]:
    return tuple(_base_name(base) for base in bases)


def _base_name(base: ast.expr) -> str:
    expr = base.value if isinstance(base, ast.Subscript) else base
    return ast.unparse(expr)


__all__ = ["Definition", "DefinitionKind", "collect_definitions"]
