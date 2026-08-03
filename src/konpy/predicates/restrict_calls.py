"""`restrictCalls` predicate: forbid call sites matching configured patterns.

Matches against both the written (as-authored) and resolved (import-followed)
dotted form of each call's callee. With `scope: "module"`, only call sites
collected at module or class scope are checked — class bodies execute at
import time just like module-level statements do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._wildcards import _matches_any
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictCallsOptionsV1

_MODULE_TIME_SCOPES = ("module", "class")


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _option_list(expected: RestrictCallsOptionsV1, key: str) -> tuple[str, ...]:
    value = _get_value(expected, key)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _option_scope(expected: RestrictCallsOptionsV1) -> Literal["any", "module"]:
    value = _get_value(expected, "scope", "any")
    return "module" if value == "module" else "any"


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


def check_restrict_calls(
    *,
    expected: RestrictCallsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag call sites whose written or resolved callee matches a forbidden pattern."""
    forbid = _option_list(expected, "forbid")
    allow = _option_list(expected, "allow")
    scope = _option_scope(expected)

    diagnostics: list[Diagnostic] = []
    for call in structure.call_sites:
        if scope == "module" and call.scope not in _MODULE_TIME_SCOPES:
            continue
        if not _is_forbidden(
            written=call.written,
            resolved=call.resolved,
            forbid=forbid,
            allow=allow,
        ):
            continue

        message = f'Call to "{call.written}" is forbidden'
        if call.resolved != call.written:
            message += f' (resolves to "{call.resolved}")'
        if scope == "module":
            message += " at module scope"

        fix_hint = (
            "Defer this call into a function so it does not run at import time."
            if scope == "module"
            else f"Remove the call to {call.written} or move it behind an allowed seam."
        )

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="restrictCalls",
                message=message,
                convention_name=convention_name,
                line=call.pos.line,
                column=call.pos.column,
                severity=severity,
                expected="no forbidden call",
                found=call.written,
                fix_hint=fix_hint,
            )
        )

    return _sort_diagnostics(diagnostics)


__all__ = ["check_restrict_calls"]
