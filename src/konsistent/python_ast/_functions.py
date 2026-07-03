from __future__ import annotations

import ast

from konsistent.python_ast._annotations import _annotation_info
from konsistent.python_ast._collector import (
    _add_declaration_symbol,
    _add_docstring_target,
    _add_export,
    _Collector,
    _position,
)
from konsistent.python_ast._dunder_all import _is_public
from konsistent.python_ast.structure import (
    ExportInfo,
    FunctionAnnotationInfo,
    FunctionInfo,
    ParamInfo,
)


def _add_function_coverage_target(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    collector: _Collector,
    *,
    qualified_name: str,
    is_public: bool,
    skip_first_self_or_cls: bool,
) -> None:
    pos = _position(node)
    _add_docstring_target(
        collector,
        kind="function",
        name=node.name,
        qualified_name=qualified_name,
        is_public=is_public,
        has_docstring=ast.get_docstring(node) is not None,
        pos=pos,
    )
    collector.function_annotation_targets.append(
        FunctionAnnotationInfo(
            name=node.name,
            qualified_name=qualified_name,
            is_public=is_public,
            params=_function_annotation_params(
                node.args,
                skip_first_self_or_cls=skip_first_self_or_cls,
            ),
            pos=pos,
            return_type=_annotation_info(node.returns),
        )
    )


def _process_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    collector: _Collector,
) -> None:
    pos = _position(node)
    collector.functions.append(
        FunctionInfo(
            name=node.name,
            params=_function_params(node.args),
            pos=pos,
            return_type=_annotation_info(node.returns),
        )
    )
    _add_function_coverage_target(
        node,
        collector,
        qualified_name=node.name,
        is_public=_is_public(node.name, collector.all_state),
        skip_first_self_or_cls=False,
    )
    _add_declaration_symbol(collector, kind="function", name=node.name, pos=pos)
    if _is_public(node.name, collector.all_state):
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=False,
                kind="function",
                name=node.name,
                pos=pos,
            ),
        )


def _function_params(args: ast.arguments) -> tuple[ParamInfo, ...]:
    return tuple(
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in [*args.posonlyargs, *args.args]
    )


def _function_annotation_params(
    args: ast.arguments,
    *,
    skip_first_self_or_cls: bool,
) -> tuple[ParamInfo, ...]:
    params = [
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in [*args.posonlyargs, *args.args]
    ]

    if args.vararg is not None:
        params.append(
            ParamInfo(
                name=args.vararg.arg,
                type_name=_annotation_info(args.vararg.annotation),
            )
        )

    params.extend(
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in args.kwonlyargs
    )

    if args.kwarg is not None:
        params.append(
            ParamInfo(
                name=args.kwarg.arg,
                type_name=_annotation_info(args.kwarg.annotation),
            )
        )

    if skip_first_self_or_cls and params and params[0].name in {"self", "cls"}:
        params = params[1:]

    return tuple(params)
