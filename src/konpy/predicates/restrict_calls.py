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
from konpy.predicates._utils import get_value, option_list, sort_diagnostics
from konpy.predicates._wildcards import is_forbidden
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictCallsOptionsV1

_MODULE_TIME_SCOPES = ("module", "class")


def _option_scope(expected: RestrictCallsOptionsV1) -> Literal["any", "module"]:
    value = get_value(expected, "scope", "any")
    return "module" if value == "module" else "any"


def check_restrict_calls(
    *,
    expected: RestrictCallsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag call sites whose written or resolved callee matches a forbidden pattern."""
    forbid = option_list(expected, "forbid")
    allow = option_list(expected, "allow")
    scope = _option_scope(expected)

    diagnostics: list[Diagnostic] = []
    for call in structure.call_sites:
        if scope == "module" and call.scope not in _MODULE_TIME_SCOPES:
            continue
        if not is_forbidden(
            candidates=(call.written, call.resolved),
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

    return sort_diagnostics(diagnostics)


__all__ = ["check_restrict_calls"]
