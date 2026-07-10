from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._restrict_annotations_matching import (
    _annotation_occurrences,
    _RestrictAnnotationMatchOptions,
    _should_report_occurrence,
)
from konpy.python_ast.structure import PyFileStructure, TypeAnnotationInfo

if TYPE_CHECKING:
    from konpy.config.schema import RestrictAnnotationsOptionsV1

_EXPECTED = "named record type (pydantic model, TypedDict, or dataclass)"
_FIX_HINT = (
    "Define a named type (pydantic model, TypedDict, or dataclass) for this record "
    "instead of an anonymous mapping."
)


@dataclass(frozen=True, kw_only=True)
class _AnnotationTarget:
    label: str
    is_public: bool
    type_name: TypeAnnotationInfo


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _option_enabled(
    expected: Literal[True] | RestrictAnnotationsOptionsV1,
    key: str,
    *,
    default: bool,
) -> bool:
    if expected is True:
        return default

    value = _get_value(expected, key)
    return default if value is None else bool(value)


def _option_list(
    expected: Literal[True] | RestrictAnnotationsOptionsV1,
    key: str,
) -> tuple[str, ...]:
    if expected is True:
        return ()

    value = _get_value(expected, key)
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _normalize_options(
    expected: Literal[True] | RestrictAnnotationsOptionsV1,
) -> _RestrictAnnotationMatchOptions:
    return _RestrictAnnotationMatchOptions(
        forbid=_option_list(expected, "forbid"),
        allow=_option_list(expected, "allow"),
        defaults=_option_enabled(expected, "defaults", default=True),
        public_only=_option_enabled(expected, "publicOnly", default=True),
    )


def _iter_function_annotation_targets(
    structure: PyFileStructure,
) -> tuple[_AnnotationTarget, ...]:
    targets: list[_AnnotationTarget] = []

    for function in structure.function_annotation_targets:
        for param in function.params:
            if param.type_name is None:
                continue
            targets.append(
                _AnnotationTarget(
                    label=(
                        f'parameter "{param.name}" of function '
                        f'"{function.qualified_name}"'
                    ),
                    is_public=function.is_public,
                    type_name=param.type_name,
                )
            )

        if function.return_type is not None:
            targets.append(
                _AnnotationTarget(
                    label=f'return of function "{function.qualified_name}"',
                    is_public=function.is_public,
                    type_name=function.return_type,
                )
            )

    return tuple(targets)


def _iter_constant_annotation_targets(
    structure: PyFileStructure,
) -> tuple[_AnnotationTarget, ...]:
    return tuple(
        _AnnotationTarget(
            label=f'module constant "{constant.name}"',
            is_public=constant.is_public,
            type_name=constant.type_name,
        )
        for constant in structure.constants
        if constant.type_name is not None
    )


def _iter_class_attribute_annotation_targets(
    structure: PyFileStructure,
) -> tuple[_AnnotationTarget, ...]:
    return tuple(
        _AnnotationTarget(
            label=f'class attribute "{attribute.qualified_name}"',
            is_public=attribute.is_public,
            type_name=attribute.type_name,
        )
        for attribute in structure.class_attributes
    )


def _iter_annotation_targets(structure: PyFileStructure) -> tuple[_AnnotationTarget, ...]:
    return (
        *_iter_function_annotation_targets(structure),
        *_iter_constant_annotation_targets(structure),
        *_iter_class_attribute_annotation_targets(structure),
    )


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(
        diagnostics,
        key=lambda diagnostic: (
            diagnostic.line if diagnostic.line is not None else -1,
            diagnostic.column if diagnostic.column is not None else -1,
            diagnostic.found or "",
        ),
    )


def check_restrict_annotations(
    *,
    expected: Literal[True] | RestrictAnnotationsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag identity-less anonymous record annotations."""
    options = _normalize_options(expected)
    diagnostics: list[Diagnostic] = []
    seen: set[tuple[int, int, str]] = set()

    for target in _iter_annotation_targets(structure):
        if options.public_only and not target.is_public:
            continue

        root_text = target.type_name.text
        for occurrence in _annotation_occurrences(target.type_name):
            if not _should_report_occurrence(
                occurrence_text=occurrence.text,
                root_text=root_text,
                options=options,
            ):
                continue

            key = (occurrence.pos.line, occurrence.pos.column, occurrence.text)
            if key in seen:
                continue
            seen.add(key)

            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="restrictAnnotations",
                    message=(
                        f'Annotation "{occurrence.text}" on {target.label} should use '
                        "a named record type"
                    ),
                    convention_name=convention_name,
                    line=occurrence.pos.line,
                    column=occurrence.pos.column,
                    severity=severity,
                    expected=_EXPECTED,
                    found=occurrence.text,
                    fix_hint=_FIX_HINT,
                )
            )

    return _sort_diagnostics(diagnostics)


__all__ = ["check_restrict_annotations"]
