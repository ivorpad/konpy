"""`restrictDecorators` predicate: forbid decorators matching configured patterns.

Matches against both the written (as-authored) and resolved (import-followed)
dotted form of each decorator, so `@pt.mark.skip` can be forbidden either by
its local alias or by its true `pytest.mark.skip` identity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import option_list, sort_diagnostics
from konpy.predicates._wildcards import is_forbidden
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictDecoratorsOptionsV1


def check_restrict_decorators(
    *,
    expected: RestrictDecoratorsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag decorators whose written or resolved form matches a forbidden pattern."""
    forbid = option_list(expected, "forbid")
    allow = option_list(expected, "allow")

    diagnostics: list[Diagnostic] = []
    for decorator in structure.decorators:
        if not is_forbidden(
            candidates=(decorator.written, decorator.resolved),
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

    return sort_diagnostics(diagnostics)


__all__ = ["check_restrict_decorators"]
