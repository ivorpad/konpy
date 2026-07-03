from __future__ import annotations

from dataclasses import dataclass

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.python_ast.structure import PyFileStructure, SourcePosition


@dataclass(frozen=True, kw_only=True)
class _Occurrence:
    name: str
    pos: SourcePosition


def _occurrences(structure: PyFileStructure, ordered_names: set[str]) -> list[_Occurrence]:
    by_name: dict[str, _Occurrence] = {}
    declared: set[str] = set()

    for symbol in structure.declaration_symbols:
        if symbol.name not in ordered_names or symbol.name in by_name:
            continue
        by_name[symbol.name] = _Occurrence(name=symbol.name, pos=symbol.pos)
        declared.add(symbol.name)

    for symbol in structure.named_export_symbols:
        if symbol.name not in ordered_names:
            continue
        if symbol.name in declared or symbol.name in by_name:
            continue
        by_name[symbol.name] = _Occurrence(name=symbol.name, pos=symbol.pos)

    return sorted(by_name.values(), key=lambda item: (item.pos.line, item.pos.column))


def check_use_declaration_order(
    *,
    expected: list[str],
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that declared symbols appear in the expected order."""
    order_by_name: dict[str, int] = {}
    for entry in expected:
        name = context.resolve_template(entry)
        order_by_name.setdefault(name, len(order_by_name))

    diagnostics: list[Diagnostic] = []
    max_seen_index = -1
    max_seen_name = ""

    for occurrence in _occurrences(structure, set(order_by_name)):
        current_index = order_by_name[occurrence.name]
        if current_index < max_seen_index:
            diagnostics.append(
                create_diagnostic(
                    file_path=context.path,
                    predicate_name="useDeclarationOrder",
                    message=(
                        f'Symbol "{occurrence.name}" must be declared '
                        f'before "{max_seen_name}"'
                    ),
                    convention_name=convention_name,
                    line=occurrence.pos.line,
                    column=occurrence.pos.column,
                    severity=severity,
                )
            )
            continue

        max_seen_index = current_index
        max_seen_name = occurrence.name

    return diagnostics
