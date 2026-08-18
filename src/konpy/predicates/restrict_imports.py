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
from konpy.predicates._utils import get_value, option_bool, option_list, sort_diagnostics
from konpy.predicates._wildcards import is_forbidden
from konpy.python_ast.structure import PyFileStructure

if TYPE_CHECKING:
    from konpy.config.schema import RestrictImportsOptionsV1

_ImportScope = Literal["any", "module", "function"]


def _option_scope(expected: RestrictImportsOptionsV1) -> _ImportScope:
    value = get_value(expected, "scope", "any")
    return value if value in ("any", "module", "function") else "any"


def check_restrict_imports(
    *,
    expected: RestrictImportsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag imports whose source or symbol path matches a forbidden pattern."""
    forbid = option_list(expected, "forbid")
    allow = option_list(expected, "allow")
    scope = _option_scope(expected)
    include_type_checking = option_bool(expected, "includeTypeChecking", default=False)

    diagnostics: list[Diagnostic] = []
    for entry in structure.scoped_imports:
        if entry.is_type and not include_type_checking:
            continue
        if scope != "any" and entry.scope != scope:
            continue
        if not is_forbidden(
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

    return sort_diagnostics(diagnostics)


__all__ = ["check_restrict_imports"]
