"""`restrictDecorators` predicate: forbid decorators matching configured patterns.

Matches against both the written (as-authored) and resolved (import-followed)
dotted form of each decorator, so `@pt.mark.skip` can be forbidden either by
its local alias or by its true `pytest.mark.skip` identity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._wildcards import _matches_any
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictDecoratorsOptionsV1


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _option_list(expected: RestrictDecoratorsOptionsV1, key: str) -> tuple[str, ...]:
    value = _get_value(expected, key)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _is_forbidden(
    *,
    written: str,
    resolved: str,
    forbid: tuple[str, ...],
    allow: tuple[str, ...],
) -> bool:
    candidates = (written, resolved)
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


def check_restrict_decorators(
    *,
    expected: RestrictDecoratorsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag decorators whose written or resolved form matches a forbidden pattern."""
    forbid = _option_list(expected, "forbid")
    allow = _option_list(expected, "allow")

    diagnostics: list[Diagnostic] = []
    for decorator in structure.decorators:
        if not _is_forbidden(
            written=decorator.written,
            resolved=decorator.resolved,
            forbid=forbid,
            allow=allow,
        ):
            continue

        message = (
            f'Decorator "@{decorator.written}" on {decorator.target_kind} '
            f'"{decorator.target_qualified_name}" is forbidden'
        )
        if decorator.resolved != decorator.written:
            message += f' (resolves to "{decorator.resolved}")'

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="restrictDecorators",
                message=message,
                convention_name=convention_name,
                line=decorator.pos.line,
                column=decorator.pos.column,
                severity=severity,
                expected="no forbidden decorator",
                found="@" + decorator.written,
                fix_hint=f"Remove @{decorator.written} or use an allowed alternative.",
            )
        )

    return _sort_diagnostics(diagnostics)


__all__ = ["check_restrict_decorators"]
