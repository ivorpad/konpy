"""Additive `expected`/`found`/`fix_hint`/`line`/`column` data for `mustNot` violations."""

from __future__ import annotations

import re

from konsistent.core._runner_messages import _IMPORT_SOURCE_GROUPS, _resolve_entry_name
from konsistent.core._runner_source_cache import _get_or_parse_file_structure
from konsistent.core._runner_types import _ForbiddenFixData
from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FileSystem
from konsistent.predicates.import_source import check_import_source
from konsistent.python_ast.structure import PyFileStructure

# The exact predicate set the `must` direction documents as able to populate
# `expected`/`found`/`fix_hint` unambiguously (see
# docs/reference/cli.md#diagnostic-intent-and-fix-direction). `mustNot`
# mirrors that same set; every other predicate leaves these fields `None`,
# matching the `must` direction's own policy of never guessing.
_RICH_MUST_NOT_KEYS: frozenset[str] = frozenset(
    {
        "importFrom",
        "matchContent",
        "havePairedFile",
        "exportClasses",
        "exportConstants",
        "haveDocstrings",
        "annotateFunctions",
        *_IMPORT_SOURCE_GROUPS,
    }
)


def _forbidden_fix_data_import_from(
    *,
    value: object,
    context: PredicateContext,
    structure: PyFileStructure,
) -> _ForbiddenFixData:
    resolved = context.resolve_template(str(value))
    match = next(
        (
            source
            for source in structure.import_sources
            if source.from_ == resolved
            or (not resolved.startswith(".") and source.from_.startswith(f"{resolved}."))
        ),
        None,
    )
    if match is None:
        return _ForbiddenFixData(expected=f'no import from "{resolved}"')

    return _ForbiddenFixData(
        expected=f'no import from "{resolved}"',
        found=match.from_,
        fix_hint=f'Remove or relocate the import of "{match.from_}".',
        line=match.pos.line,
        column=match.pos.column,
    )


def _forbidden_fix_data_import_source_group(
    *,
    key: str,
    context: PredicateContext,
    structure: PyFileStructure,
) -> _ForbiddenFixData:
    group, import_kind = _IMPORT_SOURCE_GROUPS[key]
    # `check_import_source` already has a "forbidden" branch (`expected is
    # False`) that computes the exact same fix-direction fields the `must`
    # direction uses -- reuse it for the data, but keep this call's own
    # `.message` out of it so `_format_forbidden_message`'s wording (asserted
    # by existing tests) is unaffected.
    diagnostics = check_import_source(
        expected=False,
        predicate_name=key,
        group=group,
        import_kind=import_kind,
        context=context,
        structure=structure,
    )
    if not diagnostics:
        return _ForbiddenFixData()

    diagnostic = diagnostics[0]
    return _ForbiddenFixData(
        expected=diagnostic.expected,
        found=diagnostic.found,
        fix_hint=diagnostic.fix_hint,
        line=diagnostic.line,
        column=diagnostic.column,
    )


def _forbidden_fix_data_match_content(
    *,
    pattern: str,
    context: PredicateContext,
    file_system: FileSystem,
) -> _ForbiddenFixData:
    source = file_system.read_file(context.path)
    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error:
        return _ForbiddenFixData(expected=pattern)

    match = regex.search(source)
    if match is None:
        return _ForbiddenFixData(expected=pattern)

    line = source.count("\n", 0, match.start()) + 1
    line_start = source.rfind("\n", 0, match.start()) + 1
    column = match.start() - line_start + 1

    return _ForbiddenFixData(
        expected=pattern,
        found=match.group(0),
        fix_hint=(
            f"Remove or rewrite the content in {context.path} that matches "
            f"the pattern `{pattern}`."
        ),
        line=line,
        column=column,
    )


def _forbidden_fix_data_have_paired_file(
    *,
    value: object,
    context: PredicateContext,
) -> _ForbiddenFixData:
    resolved = context.resolve_template(str(value))
    return _ForbiddenFixData(
        expected=f'no paired file at "{resolved}"',
        found=resolved,
        fix_hint=f'Delete or unpair the file at "{resolved}".',
    )


def _forbidden_fix_data_export_classes(
    *,
    value: object,
    context: PredicateContext,
    structure: PyFileStructure,
) -> _ForbiddenFixData:
    name = _resolve_entry_name(value=value, context=context)
    class_info = next((cls for cls in structure.classes if cls.name == name), None)
    if class_info is None:
        return _ForbiddenFixData(expected=f'no export of class "{name}"', found=name)

    return _ForbiddenFixData(
        expected=f'no export of class "{name}"',
        found=name,
        fix_hint=f'Remove or stop exporting class "{name}" in {context.path}.',
        line=class_info.pos.line,
        column=class_info.pos.column,
    )


def _forbidden_fix_data_export_constants(
    *,
    value: object,
    context: PredicateContext,
    structure: PyFileStructure,
) -> _ForbiddenFixData:
    name = _resolve_entry_name(value=value, context=context)
    export_info = next(
        (
            export
            for export in structure.exports
            if export.name == name and export.kind == "const" and not export.is_type
        ),
        None,
    )
    if export_info is None:
        return _ForbiddenFixData(expected=f'no export of constant "{name}"', found=name)

    return _ForbiddenFixData(
        expected=f'no export of constant "{name}"',
        found=name,
        fix_hint=f'Remove or stop exporting constant "{name}" in {context.path}.',
        line=export_info.pos.line,
        column=export_info.pos.column,
    )


def _forbidden_fix_data_have_docstrings() -> _ForbiddenFixData:
    # `haveDocstrings` evaluates an all-or-nothing condition over every
    # applicable target in the file (see `check_have_docstrings`), so --
    # unlike the item-level predicates above -- there is no single offending
    # location to anchor `line`/`column` to.
    return _ForbiddenFixData(
        expected="no docstring coverage",
        fix_hint="Remove the docstrings covered by this rule, or narrow its scope.",
    )


def _forbidden_fix_data_annotate_functions() -> _ForbiddenFixData:
    # Same all-or-nothing shape as `haveDocstrings` above.
    return _ForbiddenFixData(
        expected="no function annotation coverage",
        fix_hint="Remove the type annotations covered by this rule, or narrow its scope.",
    )


def _forbidden_fix_data(
    *,
    key: str,
    value: object,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
) -> _ForbiddenFixData:
    """Compute additive `expected`/`found`/`fix_hint`/`line`/`column` data for
    a `mustNot` violation, for the predicate set `_RICH_MUST_NOT_KEYS` names.
    Every other predicate returns an empty `_ForbiddenFixData` (all fields
    `None`), leaving its diagnostic exactly as before.
    """
    if key not in _RICH_MUST_NOT_KEYS:
        return _ForbiddenFixData()

    if key == "matchContent":
        return _forbidden_fix_data_match_content(
            pattern=str(value),
            context=context,
            file_system=file_system,
        )

    if key == "havePairedFile":
        return _forbidden_fix_data_have_paired_file(value=value, context=context)

    structure = _get_or_parse_file_structure(
        file_path=context.path,
        file_system=file_system,
        cache=file_structure_cache,
        source_cache=source_cache,
    )

    if key == "importFrom":
        return _forbidden_fix_data_import_from(value=value, context=context, structure=structure)

    if key in _IMPORT_SOURCE_GROUPS:
        return _forbidden_fix_data_import_source_group(
            key=key,
            context=context,
            structure=structure,
        )

    if key == "exportClasses":
        return _forbidden_fix_data_export_classes(
            value=value,
            context=context,
            structure=structure,
        )

    if key == "exportConstants":
        return _forbidden_fix_data_export_constants(
            value=value,
            context=context,
            structure=structure,
        )

    if key == "haveDocstrings":
        return _forbidden_fix_data_have_docstrings()

    if key == "annotateFunctions":
        return _forbidden_fix_data_annotate_functions()

    return _ForbiddenFixData()
