from __future__ import annotations

import ast

from konsistent.python_ast.structure import TypeAnnotationInfo


def _annotation_info(annotation: ast.expr | None) -> TypeAnnotationInfo | None:
    if annotation is None:
        return None
    text = ast.unparse(annotation)
    return TypeAnnotationInfo(base_name=_annotation_base_name(annotation), text=text)


def _annotation_base_name(annotation: ast.expr) -> str:
    if isinstance(annotation, ast.Subscript):
        return ast.unparse(annotation.value)
    return ast.unparse(annotation)


def _is_final_annotation(annotation: ast.expr | None) -> bool:
    return annotation is not None and _annotation_base_name(annotation) in {
        "Final",
        "typing.Final",
    }


def _is_type_alias_annotation(annotation: ast.expr | None) -> bool:
    return annotation is not None and _annotation_base_name(annotation) in {
        "TypeAlias",
        "typing.TypeAlias",
    }


def _expr_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{_expr_name(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Subscript):
        return _expr_name(expr.value)
    return ast.unparse(expr)


def _subscript_type_arguments(expr: ast.Subscript) -> tuple[str, ...]:
    if isinstance(expr.slice, ast.Tuple):
        return tuple(ast.unparse(element) for element in expr.slice.elts)
    return (ast.unparse(expr.slice),)
