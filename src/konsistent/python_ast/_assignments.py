from __future__ import annotations

import ast

from konsistent.python_ast._annotations import (
    _annotation_info,
    _is_final_annotation,
    _is_type_alias_annotation,
)
from konsistent.python_ast._collector import (
    _add_declaration_symbol,
    _add_export,
    _add_named_export_symbol,
    _Collector,
    _position,
)
from konsistent.python_ast._dunder_all import (
    _is_all_statement,
    _is_allowed_all_statement,
    _is_public,
    _target_name,
)
from konsistent.python_ast._imports import _is_type_checking_test, _TypingAliases
from konsistent.python_ast.structure import (
    ConstantInfo,
    ExportInfo,
    NamedExportSymbolInfo,
    NonBarrelStatementInfo,
    TypeAliasInfo,
)


def _process_assignment(node: ast.Assign | ast.AnnAssign, collector: _Collector) -> None:
    if _is_all_statement(node):
        return
    if isinstance(node, ast.AnnAssign) and _process_ann_assign_type_alias(
        node,
        collector,
    ):
        return
    if _process_assignment_reexport(node, collector):
        return
    _process_const_assignment(node, collector)


def _process_type_alias_statement(node: ast.TypeAlias, collector: _Collector) -> None:
    name = _target_name(node.name)
    if name is None:
        return
    pos = _position(node.name)
    collector.type_aliases.append(TypeAliasInfo(name=name, pos=pos))
    _add_declaration_symbol(collector, kind="type", name=name, pos=pos)
    if _is_public(name, collector.all_state):
        _add_export(
            collector, ExportInfo(from_=None, is_type=True, kind="type", name=name, pos=pos)
        )


def _process_ann_assign_type_alias(node: ast.AnnAssign, collector: _Collector) -> bool:
    if not _is_type_alias_annotation(node.annotation):
        return False
    name = _target_name(node.target)
    if name is None:
        return True
    pos = _position(node.target)
    collector.type_aliases.append(TypeAliasInfo(name=name, pos=pos))
    _add_declaration_symbol(collector, kind="type", name=name, pos=pos)
    if _is_public(name, collector.all_state):
        _add_export(
            collector, ExportInfo(from_=None, is_type=True, kind="type", name=name, pos=pos)
        )
    return True


def _process_assignment_reexport(
    node: ast.Assign | ast.AnnAssign,
    collector: _Collector,
) -> bool:
    target = _single_name_assignment_target(node)
    value = _assignment_value(node)
    if target is None or not isinstance(value, ast.Name):
        return False
    binding = collector.import_bindings.get(value.id)
    if binding is None or not _is_public(target.id, collector.all_state):
        return False

    pos = _position(target)
    _add_export(
        collector,
        ExportInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            kind="re-export",
            name=target.id,
            pos=pos,
        ),
    )
    _add_named_export_symbol(
        collector,
        NamedExportSymbolInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            name=target.id,
            pos=pos,
            source_name=binding.source_name,
        ),
    )
    return True


def _process_const_assignment(
    node: ast.Assign | ast.AnnAssign,
    collector: _Collector,
) -> None:
    target = _single_name_assignment_target(node)
    if target is None:
        return
    annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
    if not (_is_uppercase_constant_name(target.id) or _is_final_annotation(annotation)):
        return
    pos = _position(target)
    collector.constants.append(
        ConstantInfo(name=target.id, pos=pos, type_name=_annotation_info(annotation))
    )
    _add_declaration_symbol(collector, kind="const", name=target.id, pos=pos)
    if _is_public(target.id, collector.all_state):
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=False,
                kind="const",
                name=target.id,
                pos=pos,
            ),
        )


def _is_uppercase_constant_name(name: str) -> bool:
    return name.upper() == name and any(char.isalpha() for char in name)


def _single_name_assignment_target(node: ast.Assign | ast.AnnAssign) -> ast.Name | None:
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1:
            return None
        return node.targets[0] if isinstance(node.targets[0], ast.Name) else None
    return node.target if isinstance(node.target, ast.Name) else None


def _assignment_value(node: ast.Assign | ast.AnnAssign) -> ast.expr | None:
    return node.value


def _classify_non_barrel_statements(
    body: list[ast.stmt],
    collector: _Collector,
    aliases: _TypingAliases,
) -> None:
    for index, node in enumerate(body):
        entry = _classify_statement(
            node,
            index=index,
            collector=collector,
            aliases=aliases,
        )
        if entry is not None:
            collector.non_barrel_statements.append(entry)


def _classify_statement(
    node: ast.stmt,
    *,
    index: int,
    collector: _Collector,
    aliases: _TypingAliases,
) -> NonBarrelStatementInfo | None:
    if _is_module_docstring(node, index=index):
        return None
    if isinstance(node, ast.Import | ast.ImportFrom):
        return None
    if _is_allowed_all_statement(node):
        return None
    if isinstance(node, ast.If) and _is_type_checking_test(node.test, aliases):
        return None
    if _is_allowed_reexport_assignment(node, collector):
        return None
    if isinstance(
        node,
        ast.FunctionDef
        | ast.AsyncFunctionDef
        | ast.ClassDef
        | ast.Assign
        | ast.AnnAssign
        | ast.TypeAlias,
    ):
        return NonBarrelStatementInfo(kind="declaration", pos=_position(node))
    return NonBarrelStatementInfo(kind="expression", pos=_position(node))


def _is_module_docstring(node: ast.stmt, *, index: int) -> bool:
    return (
        index == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_allowed_reexport_assignment(node: ast.stmt, collector: _Collector) -> bool:
    if not isinstance(node, ast.Assign | ast.AnnAssign):
        return False
    target = _single_name_assignment_target(node)
    value = _assignment_value(node)
    return (
        target is not None
        and isinstance(value, ast.Name)
        and value.id in collector.import_bindings
        and _is_public(target.id, collector.all_state)
    )
