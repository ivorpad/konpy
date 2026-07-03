from __future__ import annotations

import ast

from konsistent.python_ast._annotations import _expr_name, _subscript_type_arguments
from konsistent.python_ast._collector import (
    _add_declaration_symbol,
    _add_docstring_target,
    _add_export,
    _Collector,
    _position,
)
from konsistent.python_ast._dunder_all import _is_public
from konsistent.python_ast._functions import _add_function_coverage_target
from konsistent.python_ast.structure import (
    ClassInfo,
    DeclarationSymbolKind,
    ExportInfo,
    ExportKind,
    ExtendsClauseInfo,
    InterfaceInfo,
)


def _process_class(node: ast.ClassDef, collector: _Collector) -> None:
    pos = _position(node)
    is_protocol = _is_protocol_or_abc_class(node)
    symbol_kind: DeclarationSymbolKind = "protocol" if is_protocol else "class"
    export_kind: ExportKind = "protocol" if is_protocol else "class"
    extends, implements = _class_extends_and_implements(node)
    is_public = _is_public(node.name, collector.all_state)

    collector.classes.append(
        ClassInfo(extends=extends, implements=implements, name=node.name, pos=pos)
    )
    _add_docstring_target(
        collector,
        kind="class",
        name=node.name,
        qualified_name=node.name,
        is_public=is_public,
        has_docstring=ast.get_docstring(node) is not None,
        pos=pos,
    )
    _process_class_methods(node, collector, class_is_public=is_public)

    if is_protocol:
        collector.interfaces.append(
            InterfaceInfo(extends=_class_base_infos(node), name=node.name, pos=pos)
        )

    _add_declaration_symbol(collector, kind=symbol_kind, name=node.name, pos=pos)
    if is_public:
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=is_protocol,
                kind=export_kind,
                name=node.name,
                pos=pos,
            ),
        )


def _process_class_methods(
    node: ast.ClassDef,
    collector: _Collector,
    *,
    class_is_public: bool,
) -> None:
    for body_node in node.body:
        if not isinstance(body_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        _add_function_coverage_target(
            body_node,
            collector,
            qualified_name=f"{node.name}.{body_node.name}",
            is_public=class_is_public and not body_node.name.startswith("_"),
            skip_first_self_or_cls=True,
        )


def _base_expr_name(expr: ast.expr) -> str:
    return _expr_name(expr)


def _base_type_arguments(expr: ast.expr) -> tuple[str, ...]:
    return _subscript_type_arguments(expr) if isinstance(expr, ast.Subscript) else ()


def _is_protocol_or_abc_marker(name: str) -> bool:
    return name in {"Protocol", "typing.Protocol", "ABC", "abc.ABC"}


def _is_abc_metaclass(node: ast.ClassDef) -> bool:
    return any(
        keyword.arg == "metaclass"
        and _expr_name(keyword.value) in {"ABCMeta", "abc.ABCMeta"}
        for keyword in node.keywords
    )


def _is_protocol_or_abc_class(node: ast.ClassDef) -> bool:
    return _is_abc_metaclass(node) or any(
        _is_protocol_or_abc_marker(_base_expr_name(base)) for base in node.bases
    )


def _class_base_infos(node: ast.ClassDef) -> tuple[ExtendsClauseInfo, ...]:
    infos: list[ExtendsClauseInfo] = []
    for base in node.bases:
        name = _base_expr_name(base)
        if _is_protocol_or_abc_marker(name):
            continue
        infos.append(
            ExtendsClauseInfo(name=name, type_arguments=_base_type_arguments(base))
        )
    return tuple(infos)


def _class_extends_and_implements(
    node: ast.ClassDef,
) -> tuple[str | None, tuple[str, ...]]:
    non_marker_bases = [
        _base_expr_name(base)
        for base in node.bases
        if not _is_protocol_or_abc_marker(_base_expr_name(base))
    ]
    return (
        non_marker_bases[0] if non_marker_bases else None,
        tuple(non_marker_bases[1:]),
    )
