from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._duplication_index import (
    _build_repeated_literal_index,
    _RepeatedLiteralIndex,
)
from konpy.predicates._utils import option_int, option_list, sort_diagnostics
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictRepeatedLiteralsOptionsV1

DEFAULT_MIN_LENGTH = 8
DEFAULT_MAX_OCCURRENCES = 2
_FIX_HINT = (
    "Extract the repeated string into a named constant or shared fixture and "
    "reference that name instead."
)


@dataclass(frozen=True, kw_only=True)
class _RepeatedLiteralOptions:
    min_length: int
    max_occurrences: int
    allow: tuple[str, ...]


def _normalize_options(
    expected: Literal[True] | RestrictRepeatedLiteralsOptionsV1,
) -> _RepeatedLiteralOptions:
    return _RepeatedLiteralOptions(
        min_length=option_int(expected, "minLength", default=DEFAULT_MIN_LENGTH),
        max_occurrences=option_int(
            expected,
            "maxOccurrences",
            default=DEFAULT_MAX_OCCURRENCES,
        ),
        allow=option_list(expected, "allow"),
    )


def _index_key(options: _RepeatedLiteralOptions) -> tuple[object, ...]:
    return (
        "restrictRepeatedLiterals",
        options.min_length,
        options.max_occurrences,
        options.allow,
    )


def _build_index(
    *,
    structures: Mapping[str, PyFileStructure],
    options: _RepeatedLiteralOptions,
) -> _RepeatedLiteralIndex:
    return _build_repeated_literal_index(
        structures,
        min_length=options.min_length,
        max_occurrences=options.max_occurrences,
        allow=options.allow,
    )


def check_restrict_repeated_literals(
    *,
    expected: Literal[True] | RestrictRepeatedLiteralsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag repeated string literals across the current cross-file scope."""
    del structure

    if context.cross_file is None:
        raise ValueError("restrictRepeatedLiterals requires a cross-file scope")

    options = _normalize_options(expected)
    index = context.cross_file.get_or_build_index(
        _index_key(options),
        lambda structures: _build_index(structures=structures, options=options),
    )

    expected_text = f"at most {options.max_occurrences} occurrence(s) of each string literal"
    diagnostics: list[Diagnostic] = []

    for occurrences in index.values():
        total = len(occurrences)
        for occurrence in occurrences:
            if occurrence.file_path != context.path:
                continue
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="restrictRepeatedLiterals",
                    message=(
                        f"String literal {occurrence.value!r} is repeated {total} "
                        "times across this scope; extract it into a named constant."
                    ),
                    convention_name=convention_name,
                    line=occurrence.pos.line,
                    column=occurrence.pos.column,
                    severity=severity,
                    expected=expected_text,
                    found=occurrence.value,
                    fix_hint=_FIX_HINT,
                )
            )

    return sort_diagnostics(diagnostics)


__all__ = [
    "DEFAULT_MAX_OCCURRENCES",
    "DEFAULT_MIN_LENGTH",
    "check_restrict_repeated_literals",
]
