"""`restrictImports` predicate: forbid imports matching configured patterns.

Unlike `mustNot.importFrom`, this predicate sees imports at any scope,
including ones nested inside a function body — the exact case a module-level
`importFrom` check cannot observe. Matches against both an import's source
module and its full symbol path (`pkg.Logger` bans `from pkg import Logger`
without also banning `from pkg import Other`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._wildcards import _matches_any
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictImportsOptionsV1

_ImportScope = Literal["any", "module", "function"]


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _option_list(expected: RestrictImportsOptionsV1, key: str) -> tuple[str, ...]:
    value = _get_value(expected, key)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _option_scope(expected: RestrictImportsOptionsV1) -> _ImportScope:
    value = _get_value(expected, "scope", "any")
    return value if value in ("any", "module", "function") else "any"


def _option_bool(expected: RestrictImportsOptionsV1, key: str, *, default: bool) -> bool:
    value = _get_value(expected, key, default)
    return default if value is None else bool(value)


def _is_forbidden(
    *,
    candidates: tuple[str, str],
    forbid: tuple[str, ...],
    allow: tuple[str, ...],
) -> bool:
    if not any(_matches_any(candidate, forbid) for candidate in candidates):
        return False
    return not any(_matches_any(candidate, allow) for candidate in candidates)


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(
        diagnostics,
        key=lambda diagnostic: (
            diagnostic.line if diagnostic.line is not None else -1,
            diagnostic.column if diagnostic.column is not None else -1,
            diagnostic.found or "",
        ),
    )


def check_restrict_imports(
    *,
    expected: RestrictImportsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag imports whose source or symbol path matches a forbidden pattern."""
    forbid = _option_list(expected, "forbid")
    allow = _option_list(expected, "allow")
    scope = _option_scope(expected)
    include_type_checking = _option_bool(expected, "includeTypeChecking", default=False)

    diagnostics: list[Diagnostic] = []
    for entry in structure.scoped_imports:
        if entry.is_type and not include_type_checking:
            continue
        if scope != "any" and entry.scope != scope:
            continue
        if not _is_forbidden(
            candidates=(entry.source, entry.symbol_path),
            forbid=forbid,
            allow=allow,
        ):
            continue

        message = f'Import of "{entry.symbol_path}" is forbidden'
        if entry.scope == "function":
            message += " (function-scoped import)"

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="restrictImports",
                message=message,
                convention_name=convention_name,
                line=entry.pos.line,
                column=entry.pos.column,
                severity=severity,
                expected="no forbidden import",
                found=entry.symbol_path,
                fix_hint="Remove the import or import an allowed module instead.",
            )
        )

    return _sort_diagnostics(diagnostics)


__all__ = ["check_restrict_imports"]
