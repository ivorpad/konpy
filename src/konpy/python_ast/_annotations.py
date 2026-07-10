from __future__ import annotations

import ast

from konpy.python_ast.structure import (
    AnnotationTextOccurrenceInfo,
    SourcePosition,
    TypeAnnotationInfo,
)


def _annotation_info(annotation: ast.expr | None) -> TypeAnnotationInfo | None:
    if annotation is None:
        return None
    text = ast.unparse(annotation)
    return TypeAnnotationInfo(
        base_name=_annotation_base_name(annotation),
        text=text,
        pos=_position(annotation),
        occurrences=_annotation_occurrences(annotation, root_text=text),
    )


def _position(node: ast.AST) -> SourcePosition:
    return SourcePosition(
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _annotation_occurrences(
    annotation: ast.expr,
    *,
    root_text: str,
) -> tuple[AnnotationTextOccurrenceInfo, ...]:
    occurrences = [
        AnnotationTextOccurrenceInfo(
            text=root_text,
            pos=_position(annotation),
            is_root=True,
        )
    ]

    occurrences.extend(
        AnnotationTextOccurrenceInfo(
            text=ast.unparse(node),
            pos=_position(node),
            is_root=False,
        )
        for node in _nested_subscripts_preorder(annotation)
    )
    return tuple(occurrences)


def _nested_subscripts_preorder(node: ast.AST) -> tuple[ast.Subscript, ...]:
    results: list[ast.Subscript] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Subscript):
            results.append(child)
        results.extend(_nested_subscripts_preorder(child))
    return tuple(results)


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
