from __future__ import annotations

import ast
from dataclasses import dataclass

from konpy.predicates._wildcards import _matches_any
from konpy.python_ast.structure import (
    AnnotationTextOccurrenceInfo,
    TypeAnnotationInfo,
)

_MAPPING_BASES = {
    "dict",
    "Dict",
    "Mapping",
    "MutableMapping",
    "OrderedDict",
    "defaultdict",
}
_UNION_BASES = {"Union", "Optional"}
_BROAD_VALUE_BASES = {"Any", "object"}


@dataclass(frozen=True, kw_only=True)
class _RestrictAnnotationMatchOptions:
    forbid: tuple[str, ...]
    allow: tuple[str, ...]
    defaults: bool
    public_only: bool


def _annotation_occurrences(
    type_name: TypeAnnotationInfo,
) -> tuple[AnnotationTextOccurrenceInfo, ...]:
    if type_name.occurrences:
        return type_name.occurrences
    if type_name.pos is None:
        return ()
    return (
        AnnotationTextOccurrenceInfo(
            text=type_name.text,
            pos=type_name.pos,
            is_root=True,
        ),
    )


def _is_allowed(
    *,
    occurrence_text: str,
    root_text: str,
    allow: tuple[str, ...],
) -> bool:
    return _matches_any(occurrence_text, allow) or _matches_any(root_text, allow)


def _parse_expr(text: str) -> ast.expr | None:
    try:
        return ast.parse(text, mode="eval").body
    except SyntaxError:
        return None


def _final_segment_from_expr(expr: ast.expr) -> str:
    return ast.unparse(expr).split(".")[-1]


def _subscript_args(expr: ast.Subscript) -> tuple[ast.expr, ...]:
    if isinstance(expr.slice, ast.Tuple):
        return tuple(expr.slice.elts)
    return (expr.slice,)


def _is_string_key(expr: ast.expr) -> bool:
    return _final_segment_from_expr(expr) == "str"


def _is_union_syntax(expr: ast.expr) -> bool:
    return isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr)


def _is_union_or_optional_subscript(expr: ast.expr) -> bool:
    if not isinstance(expr, ast.Subscript):
        return False
    return _final_segment_from_expr(expr.value) in _UNION_BASES


def _is_any_or_object(expr: ast.expr) -> bool:
    return _final_segment_from_expr(expr) in _BROAD_VALUE_BASES


def _is_broad_mapping_value(expr: ast.expr) -> bool:
    return (
        _is_union_syntax(expr)
        or _is_union_or_optional_subscript(expr)
        or _is_any_or_object(expr)
    )


def _is_default_restricted_annotation(text: str) -> bool:
    expr = _parse_expr(text)
    if not isinstance(expr, ast.Subscript):
        return False

    if _final_segment_from_expr(expr.value) not in _MAPPING_BASES:
        return False

    args = _subscript_args(expr)
    if len(args) < 2:
        return False

    key_type, value_type = args[0], args[1]
    return _is_string_key(key_type) and _is_broad_mapping_value(value_type)


def _should_report_occurrence(
    *,
    occurrence_text: str,
    root_text: str,
    options: _RestrictAnnotationMatchOptions,
) -> bool:
    if _is_allowed(
        occurrence_text=occurrence_text,
        root_text=root_text,
        allow=options.allow,
    ):
        return False

    if _matches_any(occurrence_text, options.forbid):
        return True

    return options.defaults and _is_default_restricted_annotation(occurrence_text)


__all__: list[str] = []
