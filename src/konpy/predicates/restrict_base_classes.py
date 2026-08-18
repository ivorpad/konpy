"""`restrictBaseClasses` predicate: forbid base classes matching configured patterns.

Matches against both the written (as-authored) and resolved (import-followed)
dotted form of each base class reference, so `class X(BM)` can be forbidden
either by its local alias or by its true `pydantic.BaseModel` identity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.predicates._utils import option_list, sort_diagnostics
from konpy.predicates._wildcards import is_forbidden
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictBaseClassesOptionsV1


def check_restrict_base_classes(
    *,
    expected: RestrictBaseClassesOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag base classes whose written or resolved form matches a forbidden pattern."""
    forbid = option_list(expected, "forbid")
    allow = option_list(expected, "allow")

    diagnostics: list[Diagnostic] = []
    for base in structure.base_class_refs:
        if not is_forbidden(
            candidates=(base.written, base.resolved),
            forbid=forbid,
            allow=allow,
        ):
            continue

        message = f'Base class "{base.written}" of class "{base.class_qualified_name}" is forbidden'
        if base.resolved != base.written:
            message += f' (resolves to "{base.resolved}")'

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="restrictBaseClasses",
                message=message,
                convention_name=convention_name,
                line=base.pos.line,
                column=base.pos.column,
                severity=severity,
                expected="no forbidden base class",
                found=base.written,
                fix_hint=(
                    "Inherit from an allowed base or compose instead of "
                    f"subclassing {base.written}."
                ),
            )
        )

    return sort_diagnostics(diagnostics)


__all__ = ["check_restrict_base_classes"]
