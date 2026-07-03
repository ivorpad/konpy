from __future__ import annotations

from typing import Literal

from konsistent.config.schema import HaveDocstringsOptionsV1
from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.predicates._utils import get_value
from konsistent.python_ast.structure import DocstringTargetInfo, PyFileStructure


def _option_enabled(
    expected: Literal[True] | HaveDocstringsOptionsV1, key: str, *, default: bool
) -> bool:
    if expected is True:
        return default

    value = get_value(expected, key)
    return default if value is None else bool(value)


def _message(target: DocstringTargetInfo) -> str:
    match target.kind:
        case "module":
            return "Missing module docstring"
        case "class":
            return f'Class "{target.qualified_name}" must have a docstring'
        case "function":
            return f'Function "{target.qualified_name}" must have a docstring'


def _expected_label(target: DocstringTargetInfo) -> str:
    match target.kind:
        case "module":
            return "module docstring"
        case "class":
            return f'docstring on class "{target.qualified_name}"'
        case "function":
            return f'docstring on function "{target.qualified_name}"'


def _fix_hint(target: DocstringTargetInfo) -> str:
    match target.kind:
        case "module":
            return "Add a module-level docstring as the first statement of the file."
        case "class":
            return f'Add a docstring to class "{target.qualified_name}".'
        case "function":
            return f'Add a docstring to function "{target.qualified_name}".'


def check_have_docstrings(
    *,
    expected: Literal[True] | HaveDocstringsOptionsV1,
    context: PredicateContext,
    structure: PyFileStructure,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Check that modules, classes, and/or functions have docstrings per the given options."""
    check_modules = _option_enabled(expected, "modules", default=True)
    check_classes = _option_enabled(expected, "classes", default=True)
    check_functions = _option_enabled(expected, "functions", default=True)
    public_only = _option_enabled(expected, "publicOnly", default=True)

    diagnostics: list[Diagnostic] = []

    for target in structure.docstring_targets:
        if target.kind == "module" and not check_modules:
            continue
        if target.kind == "class" and not check_classes:
            continue
        if target.kind == "function" and not check_functions:
            continue
        if public_only and target.kind != "module" and not target.is_public:
            continue
        if target.has_docstring:
            continue

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name="haveDocstrings",
                message=_message(target),
                convention_name=convention_name,
                line=target.pos.line,
                column=target.pos.column,
                severity=severity,
                expected=_expected_label(target),
                fix_hint=_fix_hint(target),
            )
        )

    return diagnostics
