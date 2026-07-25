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
from collections import deque
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
    # Root modules the owning class's import-backed bases come from (sorted,
    # deduped): `import acp` + `class A(acp.Agent)` -> ("acp",). Locally
    # defined and relative-import bases contribute nothing.
    class_base_roots: tuple[str, ...] = ()


def collect_definitions(*, module: ast.Module, module_path: str) -> list[Definition]:
    """Collect module-level and one-level-of-class-body definitions from `module`."""
    definitions: list[Definition] = []
    import_scope = _module_import_scope(module)

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
            definitions.extend(
                _collect_class_members(
                    node=node, module_path=module_path, import_scope=import_scope
                )
            )
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


def _collect_class_members(
    *, node: ast.ClassDef, module_path: str, import_scope: _ModuleImportScope
) -> list[Definition]:
    bases = _base_names(node.bases)
    base_roots = _base_roots(bases, import_scope)
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
                    class_base_roots=base_roots,
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
                        class_base_roots=base_roots,
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
    class_base_roots: tuple[str, ...] = (),
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
        class_base_roots=class_base_roots,
    )


@dataclass(frozen=True, kw_only=True)
class _ModuleImportScope:
    """Module-scope import bindings relevant to resolving class-base origins."""

    # Imported binding name -> root module ("" for relative imports, which
    # read as repo-local downstream).
    named: dict[str, str]
    # Root modules of `from x import *` statements: any base name that is
    # neither imported by name nor defined at module scope may come from one
    # of these.
    star_roots: tuple[str, ...]
    # Names bound at module scope (classes, assignments) — a base matching
    # one is locally defined, never star-imported.
    local_names: frozenset[str]


def _module_import_scope(module: ast.Module) -> _ModuleImportScope:
    """Scan module-scope statements only (into `if`/`try`, not into function
    or class bodies) so a function-local alias cannot shadow the module-level
    import that class bases actually resolve to."""
    named: dict[str, str] = {}
    star_roots: set[str] = set()
    local_names: set[str] = set()

    queue: deque[ast.stmt] = deque(module.body)
    while queue:
        node = queue.popleft()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            local_names.add(node.name)
            continue
        if isinstance(node, ast.ClassDef):
            local_names.add(node.name)
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                named[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom):
            root = "" if node.level else (node.module or "").split(".", 1)[0]
            for alias in node.names:
                if alias.name == "*":
                    if root:
                        star_roots.add(root)
                else:
                    named[alias.asname or alias.name] = root
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            local_names.update(target.id for target in _name_targets(node))
        else:
            queue.extend(
                child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt)
            )

    return _ModuleImportScope(
        named=named,
        star_roots=tuple(sorted(star_roots)),
        local_names=frozenset(local_names),
    )


def _base_roots(bases: tuple[str, ...], scope: _ModuleImportScope) -> tuple[str, ...]:
    roots: set[str] = set()
    for base in bases:
        first = base.split(".", 1)[0]
        if first in scope.named:
            if scope.named[first]:
                roots.add(scope.named[first])
        elif first not in scope.local_names:
            # Unresolvable base in a module with star imports: attribute it
            # to those — a framework base pulled in via `import *` must not
            # lose the protocol-override exemption.
            roots.update(scope.star_roots)
    return tuple(sorted(roots))


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
