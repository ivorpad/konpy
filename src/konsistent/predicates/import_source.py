from __future__ import annotations

from typing import Literal

from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.python_ast.structure import ImportSourceInfo, PyFileStructure

ImportSourceGroup = Literal["currentDir", "parents", "externals"]
ImportKind = Literal["value", "type"]


def _in_group(source: ImportSourceInfo, group: ImportSourceGroup) -> bool:
    match group:
        case "currentDir":
            return source.level == 1
        case "parents":
            return source.level >= 2
        case "externals":
            return source.level == 0


def _group_label(group: ImportSourceGroup) -> str:
    match group:
        case "currentDir":
            return "current directory"
        case "parents":
            return "parent directories"
        case "externals":
            return "external packages"


def _example_import(group: ImportSourceGroup, *, is_type: bool) -> str:
    match group:
        case "currentDir":
            example = "from .module import Name"
        case "parents":
            example = "from ..module import Name"
        case "externals":
            example = "import package_name"
    if is_type:
        return f"`{example}` inside an `if TYPE_CHECKING:` block"
    return f"`{example}`"


def check_import_source(
    *,
    expected: bool,
    predicate_name: str,
    group: ImportSourceGroup,
    import_kind: ImportKind,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    is_type = import_kind == "type"
    found = next(
        (
            source
            for source in structure.import_sources
            if source.is_type == is_type and _in_group(source, group)
        ),
        None,
    )
    label = _group_label(group)
    noun = "type import" if is_type else "import"
    capitalized = "Type import" if is_type else "Import"

    if expected and found is None:
        return [
            create_diagnostic(
                file_path=context.path,
                predicate_name=predicate_name,
                message=f"Missing {noun} from {label}",
                convention_name=convention_name,
                severity=severity,
                expected=f"{noun} from {label}",
                fix_hint=f"Add {noun} such as {_example_import(group, is_type=is_type)}.",
            )
        ]

    if not expected and found is not None:
        return [
            create_diagnostic(
                file_path=context.path,
                predicate_name=predicate_name,
                message=f"{capitalized} from {label} is not allowed",
                convention_name=convention_name,
                line=found.pos.line,
                column=found.pos.column,
                severity=severity,
                expected=f"no {noun} from {label}",
                found=found.from_,
                fix_hint=f'Remove or relocate the {noun} of "{found.from_}".',
            )
        ]

    return []
