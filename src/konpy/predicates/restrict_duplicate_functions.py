from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._duplication_index import (
    _build_duplicate_function_index,
    _DuplicateFunctionIndex,
)
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictDuplicateFunctionsOptionsV1

DEFAULT_MIN_STATEMENTS = 4
# Public (not module-private) because `konpy improve` reuses this exact
# wording in its finding block -- the agent should see the same fix guidance
# a `konpy check` diagnostic would show for this violation.
FIX_HINT = (
    "Extract the shared implementation into one helper and call it from the "
    "duplicate functions, or make the implementations meaningfully different."
)


@dataclass(frozen=True, kw_only=True)
class _DuplicateFunctionOptions:
    min_statements: int
    public_only: bool
    allow_names: tuple[str, ...]


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _option_int(
    expected: Literal[True] | RestrictDuplicateFunctionsOptionsV1,
    key: str,
    *,
    default: int,
) -> int:
    if expected is True:
        return default
    value = _get_value(expected, key)
    return default if not isinstance(value, int | str) else int(value)


def _option_bool(
    expected: Literal[True] | RestrictDuplicateFunctionsOptionsV1,
    key: str,
    *,
    default: bool,
) -> bool:
    if expected is True:
        return default
    value = _get_value(expected, key)
    return default if value is None else bool(value)


def _option_list(
    expected: Literal[True] | RestrictDuplicateFunctionsOptionsV1,
    key: str,
) -> tuple[str, ...]:
    if expected is True:
        return ()

    value = _get_value(expected, key)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _normalize_options(
    expected: Literal[True] | RestrictDuplicateFunctionsOptionsV1,
) -> _DuplicateFunctionOptions:
    return _DuplicateFunctionOptions(
        min_statements=_option_int(
            expected,
            "minStatements",
            default=DEFAULT_MIN_STATEMENTS,
        ),
        public_only=_option_bool(expected, "publicOnly", default=False),
        allow_names=_option_list(expected, "allowNames"),
    )


def _index_key(options: _DuplicateFunctionOptions) -> tuple[object, ...]:
    return (
        "restrictDuplicateFunctions",
        options.min_statements,
        options.public_only,
        options.allow_names,
    )


def _build_index(
    *,
    structures: Mapping[str, PyFileStructure],
    options: _DuplicateFunctionOptions,
) -> _DuplicateFunctionIndex:
    return _build_duplicate_function_index(
        structures,
        min_statements=options.min_statements,
        public_only=options.public_only,
        allow_names=options.allow_names,
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


def check_restrict_duplicate_functions(
    *,
    expected: Literal[True] | RestrictDuplicateFunctionsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag duplicate function implementations across the current cross-file scope."""
    del structure

    if context.cross_file is None:
        raise ValueError("restrictDuplicateFunctions requires a cross-file scope")

    options = _normalize_options(expected)
    index = context.cross_file.get_or_build_index(
        _index_key(options),
        lambda structures: _build_index(structures=structures, options=options),
    )

    diagnostics: list[Diagnostic] = []

    for group in index.values():
        canonical = group.canonical
        canonical_label = f"{canonical.file_path}::{canonical.qualified_name}"
        for duplicate in group.duplicates:
            if duplicate.file_path != context.path:
                continue
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="restrictDuplicateFunctions",
                    message=(
                        f'Function "{duplicate.qualified_name}" duplicates the '
                        f'implementation of "{canonical_label}"'
                    ),
                    convention_name=convention_name,
                    line=duplicate.pos.line,
                    column=duplicate.pos.column,
                    severity=severity,
                    expected="unique function implementation",
                    found=f"duplicate of {canonical_label}",
                    fix_hint=FIX_HINT,
                )
            )

    return _sort_diagnostics(diagnostics)


__all__ = ["DEFAULT_MIN_STATEMENTS", "FIX_HINT", "check_restrict_duplicate_functions"]
