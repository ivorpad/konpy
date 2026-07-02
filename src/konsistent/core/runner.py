from __future__ import annotations

import posixpath
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from konsistent.config.schema import ConfigV1, MustBlockV1, MustPredicatesV1
from konsistent.core.case_utils import derive_camel_to_pascal_map, invert_map
from konsistent.core.constraints import (
    parse_placeholder_constraint,
    validate_placeholder_constraint,
)
from konsistent.core.context import PredicateContext, build_context
from konsistent.core.convention_name import generate_convention_name
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FileSystem
from konsistent.core.path_matcher import MatchedPath, match_paths
from konsistent.core.placeholders import PlaceholderValue
from konsistent.core.suppressions import (
    SuppressedDiagnostic,
    filter_suppressed_diagnostics,
    parse_suppressions_for_source,
)
from konsistent.predicates.import_source import check_import_source
from konsistent.predicates.registry import (
    PredicateRegistry,
    builtin_predicate_registry,
    iter_predicate_items,
)
from konsistent.python_ast.parser import parse_file_structure
from konsistent.python_ast.structure import PyFileStructure
from konsistent.unused.engine import CONVENTION_NAME as UNUSED_CONVENTION_NAME
from konsistent.unused.engine import run_unused_code_with_metadata


@dataclass(frozen=True, kw_only=True)
class RunResult:
    diagnostics: list[Diagnostic]
    files_checked: int
    duration_ms: float | None
    suppressed_diagnostics: list[SuppressedDiagnostic] = field(default_factory=list)


CaseMaps = dict[str, dict[str, str] | None]


@dataclass(frozen=True, kw_only=True)
class _MustNotCheck:
    key: str
    predicate: MustPredicatesV1
    value: Any


def _build_static_placeholders(
    *,
    raw: Mapping[str, str] | None,
    case_maps: CaseMaps,
) -> dict[str, PlaceholderValue]:
    if raw is None:
        return {}

    return {
        name: PlaceholderValue(
            value,
            kebab_to_pascal_map=case_maps["kebab_to_pascal_map"],
            kebab_to_camel_map=case_maps["kebab_to_camel_map"],
            pascal_to_kebab_map=case_maps["pascal_to_kebab_map"],
            camel_to_kebab_map=case_maps["camel_to_kebab_map"],
            camel_to_pascal_map=case_maps["camel_to_pascal_map"],
            pascal_to_camel_map=case_maps["pascal_to_camel_map"],
        )
        for name, value in raw.items()
    }


def _normalize_must_blocks(
    *,
    must: MustPredicatesV1 | list[MustBlockV1] | None,
    must_not: MustPredicatesV1 | None,
    predicate_registry: PredicateRegistry,
) -> list[MustBlockV1]:
    context = predicate_registry.validation_context()

    if isinstance(must, list):
        blocks = list(must)
        if must_not is not None:
            blocks.append(MustBlockV1.model_validate({"mustNot": must_not}, context=context))
        return blocks

    if must is not None and must_not is not None:
        return [
            MustBlockV1.model_validate(
                {"must": must, "mustNot": must_not},
                context=context,
            )
        ]

    if must is not None:
        return [MustBlockV1.model_validate({"must": must}, context=context)]

    if must_not is not None:
        return [MustBlockV1.model_validate({"mustNot": must_not}, context=context)]

    return []


def _resolve_block_convention_name(
    *,
    block: MustBlockV1,
    convention_name: str,
) -> str:
    return block.name or convention_name


def _with_convention_metadata(
    diagnostics: list[Diagnostic],
    *,
    description: str | None,
    hint: str | None,
) -> list[Diagnostic]:
    if description is None and hint is None:
        return diagnostics

    return [
        replace(
            diagnostic,
            description=diagnostic.description or description,
            hint=diagnostic.hint or hint,
        )
        for diagnostic in diagnostics
    ]


def _is_file_excluded(
    *,
    file_path: str,
    exclude_files: list[str] | None,
    context: PredicateContext,
) -> bool:
    if not exclude_files:
        return False

    for pattern in exclude_files:
        resolved = context.resolve_template(pattern)
        if file_path == resolved or posixpath.basename(file_path) == resolved:
            return True

    return False


def _evaluate_placeholder_satisfies(
    *,
    raw: str,
    context: PredicateContext,
) -> bool:
    colon_index = raw.find(":")
    if colon_index < 1:
        return False

    name = raw[:colon_index]
    constraint_raw = raw[colon_index + 1 :]
    placeholder = context.placeholders.get(name)
    if placeholder is None:
        return False

    constraint = parse_placeholder_constraint(constraint_raw)
    if constraint is None:
        return False

    return validate_placeholder_constraint(placeholder.raw, constraint)


def _evaluate_condition(
    *,
    block: MustBlockV1,
    context: PredicateContext,
) -> bool:
    condition = block.if_
    if condition is None:
        return True

    has_file = getattr(condition, "hasFile", None)
    if has_file is not None:
        return context.file_exists(context.resolve_template(has_file))

    placeholder_satisfies = getattr(condition, "placeholderSatisfies", None)
    if placeholder_satisfies is None:
        return False

    return _evaluate_placeholder_satisfies(
        raw=placeholder_satisfies,
        context=context,
    )


def _get_or_parse_file_structure(
    *,
    file_path: str,
    file_system: FileSystem,
    cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
) -> PyFileStructure:
    cached = cache.get(file_path)
    if cached is not None:
        return cached

    source = _read_source_with_cache(
        file_path=file_path,
        file_system=file_system,
        source_cache=source_cache,
    )
    structure = parse_file_structure(source, file_path)
    cache[file_path] = structure
    return structure


def _check_must_predicates(
    *,
    must: MustPredicatesV1,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    items = iter_predicate_items(must)
    diagnostics: list[Diagnostic] = []

    structure: PyFileStructure | None = None
    if any(key in predicate_registry.ast_predicates for key, _value in items):
        structure = _get_or_parse_file_structure(
            file_path=context.path,
            file_system=file_system,
            cache=file_structure_cache,
            source_cache=source_cache,
        )

    for key, value in items:
        handler = predicate_registry.handlers.get(key)
        if handler is None:
            continue

        diagnostics.extend(
            handler(
                value,
                context,
                file_system,
                structure,
                convention_name,
                severity,
            )
        )

    return diagnostics


def _get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _resolve_entry_name(
    *,
    value: Any,
    context: PredicateContext,
) -> str:
    if isinstance(value, str):
        return context.resolve_template(value)

    name = _get_value(value, "name")
    if isinstance(name, str):
        return context.resolve_template(name)

    return "unknown"


def _format_forbidden_message(
    *,
    key: str,
    value: Any,
    context: PredicateContext,
    predicate_registry: PredicateRegistry,
) -> str:
    plugin_message_provider = predicate_registry.plugin_forbidden_messages.get(key)
    if plugin_message_provider is not None:
        return plugin_message_provider(value, context)

    name = _resolve_entry_name(value=value, context=context)

    match key:
        case "haveType":
            return f'Forbidden path type "{value}"'
        case "haveFiles":
            return f'Forbidden file "{context.resolve_template(str(value))}"'
        case "matchContent":
            return f'Forbidden content matching regex "{value}"'
        case "havePairedFile":
            return f'Forbidden paired file "{context.resolve_template(str(value))}"'
        case "declareTypes":
            return f'Forbidden type declaration "{name}"'
        case "declareConstants":
            return f'Forbidden constant declaration "{name}"'
        case "declareFunctions":
            return f'Forbidden function declaration "{name}"'
        case "declareInterfaces":
            return f'Forbidden interface declaration "{name}"'
        case "declareClasses":
            return f'Forbidden class declaration "{name}"'
        case "export":
            return f'Forbidden export "{name}"'
        case "exportTypes":
            return f'Forbidden type export "{name}"'
        case "exportConstants":
            return f'Forbidden constant export "{name}"'
        case "exportFunctions":
            return f'Forbidden function export "{name}"'
        case "exportInterfaces":
            return f'Forbidden interface export "{name}"'
        case "exportClasses":
            return f'Forbidden class export "{name}"'
        case "import":
            return f'Forbidden import "{name}"'
        case "importFrom":
            return f'Forbidden import from "{context.resolve_template(str(value))}"'
        case "importTypes":
            return f'Forbidden type import "{name}"'
        case "importFromCurrentDir":
            if value is False:
                return "Missing import from current directory is not allowed"
            return "Forbidden import from current directory"
        case "importFromParents":
            if value is False:
                return "Missing import from parent directories is not allowed"
            return "Forbidden import from parent directories"
        case "importFromExternals":
            if value is False:
                return "Missing import from external packages is not allowed"
            return "Forbidden import from external packages"
        case "importTypesFromCurrentDir":
            if value is False:
                return "Missing type import from current directory is not allowed"
            return "Forbidden type import from current directory"
        case "importTypesFromParents":
            if value is False:
                return "Missing type import from parent directories is not allowed"
            return "Forbidden type import from parent directories"
        case "importTypesFromExternals":
            if value is False:
                return "Missing type import from external packages is not allowed"
            return "Forbidden type import from external packages"
        case "useDeclarationOrder":
            entries = value if isinstance(value, list) else [str(value)]
            resolved = [context.resolve_template(entry) for entry in entries]
            joined = '", "'.join(resolved)
            return f'Forbidden declaration order "{joined}"'
        case "areBarrelFiles":
            if value is False:
                return "Forbidden non-barrel file"
            return "Forbidden barrel file"
        case "haveDocstrings":
            return "Forbidden docstring coverage"
        case "annotateFunctions":
            return "Forbidden function annotation coverage"
        case _:
            return f"Forbidden {key}"


_IMPORT_SOURCE_GROUPS: dict[str, tuple[str, str]] = {
    "importFromCurrentDir": ("currentDir", "value"),
    "importFromParents": ("parents", "value"),
    "importFromExternals": ("externals", "value"),
    "importTypesFromCurrentDir": ("currentDir", "type"),
    "importTypesFromParents": ("parents", "type"),
    "importTypesFromExternals": ("externals", "type"),
}

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


@dataclass(frozen=True, kw_only=True)
class _ForbiddenFixData:
    expected: str | None = None
    found: str | None = None
    fix_hint: str | None = None
    line: int | None = None
    column: int | None = None


def _forbidden_fix_data_import_from(
    *,
    value: Any,
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
    value: Any,
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
    value: Any,
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
    value: Any,
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
    value: Any,
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


def _build_singleton_predicate(
    *,
    key: str,
    value: Any,
    predicate_registry: PredicateRegistry,
) -> MustPredicatesV1:
    return MustPredicatesV1.model_validate(
        {key: value},
        context=predicate_registry.validation_context(),
    )


def _build_must_not_checks(
    *,
    must_not: MustPredicatesV1,
    predicate_registry: PredicateRegistry,
) -> list[_MustNotCheck]:
    checks: list[_MustNotCheck] = []

    for key, value in iter_predicate_items(must_not):
        if isinstance(value, list) and key in predicate_registry.item_level_must_not_predicates:
            for item in value:
                checks.append(
                    _MustNotCheck(
                        key=key,
                        predicate=_build_singleton_predicate(
                            key=key,
                            value=[item],
                            predicate_registry=predicate_registry,
                        ),
                        value=item,
                    )
                )
            continue

        checks.append(
            _MustNotCheck(
                key=key,
                predicate=_build_singleton_predicate(
                    key=key,
                    value=value,
                    predicate_registry=predicate_registry,
                ),
                value=value,
            )
        )

    return checks


def _check_must_not_predicates(
    *,
    must_not: MustPredicatesV1,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for check in _build_must_not_checks(
        must_not=must_not,
        predicate_registry=predicate_registry,
    ):
        normal_diagnostics = _check_must_predicates(
            must=check.predicate,
            convention_name=convention_name,
            context=context,
            file_system=file_system,
            file_structure_cache=file_structure_cache,
            source_cache=source_cache,
            severity=severity,
            predicate_registry=predicate_registry,
        )
        if normal_diagnostics:
            continue

        fix_data = _forbidden_fix_data(
            key=check.key,
            value=check.value,
            context=context,
            file_system=file_system,
            file_structure_cache=file_structure_cache,
            source_cache=source_cache,
        )

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name=f"mustNot.{check.key}",
                message=_format_forbidden_message(
                    key=check.key,
                    value=check.value,
                    context=context,
                    predicate_registry=predicate_registry,
                ),
                convention_name=convention_name,
                severity=severity,
                expected=fix_data.expected,
                found=fix_data.found,
                fix_hint=fix_data.fix_hint,
                line=fix_data.line,
                column=fix_data.column,
            )
        )

    return diagnostics


def _check_predicates(
    *,
    must: MustPredicatesV1 | None,
    must_not: MustPredicatesV1 | None,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if must is not None:
        diagnostics.extend(
            _check_must_predicates(
                must=must,
                convention_name=convention_name,
                context=context,
                file_system=file_system,
                file_structure_cache=file_structure_cache,
                source_cache=source_cache,
                severity=severity,
                predicate_registry=predicate_registry,
            )
        )

    if must_not is not None:
        diagnostics.extend(
            _check_must_not_predicates(
                must_not=must_not,
                convention_name=convention_name,
                context=context,
                file_system=file_system,
                file_structure_cache=file_structure_cache,
                source_cache=source_cache,
                severity=severity,
                predicate_registry=predicate_registry,
            )
        )

    return diagnostics


def _match_with_case_maps(
    *,
    patterns: list[str],
    file_system: FileSystem,
    case_maps: CaseMaps,
) -> list[MatchedPath]:
    return match_paths(
        patterns=patterns,
        file_system=file_system,
        kebab_to_pascal_map=case_maps["kebab_to_pascal_map"],
        kebab_to_camel_map=case_maps["kebab_to_camel_map"],
        pascal_to_kebab_map=case_maps["pascal_to_kebab_map"],
        camel_to_kebab_map=case_maps["camel_to_kebab_map"],
        camel_to_pascal_map=case_maps["camel_to_pascal_map"],
        pascal_to_camel_map=case_maps["pascal_to_camel_map"],
    )


def _evaluate_for_block(
    *,
    block: MustBlockV1,
    parent_context: PredicateContext,
    file_system: FileSystem,
    convention_name: str | None,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    checked_paths: set[str],
    case_maps: CaseMaps,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    if block.for_ is None:
        if _is_file_excluded(
            file_path=parent_context.path,
            exclude_files=block.excludeFiles,
            context=parent_context,
        ):
            return []

        return _check_predicates(
            must=block.must,
            must_not=block.mustNot,
            convention_name=convention_name,
            context=parent_context,
            file_system=file_system,
            file_structure_cache=file_structure_cache,
            source_cache=source_cache,
            severity=severity,
            predicate_registry=predicate_registry,
        )

    raw_files = block.for_.files
    file_patterns = raw_files if isinstance(raw_files, list) else [raw_files]
    full_patterns = [
        posixpath.join(parent_context.base_path, parent_context.resolve_template(pattern))
        for pattern in file_patterns
    ]

    matched = _match_with_case_maps(
        patterns=full_patterns,
        file_system=file_system,
        case_maps=case_maps,
    )

    if not matched:
        return []

    diagnostics: list[Diagnostic] = []

    for entry in matched:
        checked_paths.add(entry.path)
        merged_placeholders = dict(entry.placeholders)
        merged_placeholders.update(parent_context.placeholders)

        for_context = build_context(
            matched=MatchedPath(
                path=entry.path,
                placeholders=merged_placeholders,
            ),
            file_system=file_system,
        )

        if _is_file_excluded(
            file_path=entry.path,
            exclude_files=block.excludeFiles,
            context=for_context,
        ):
            continue

        diagnostics.extend(
            _check_predicates(
                must=block.must,
                must_not=block.mustNot,
                convention_name=convention_name,
                context=for_context,
                file_system=file_system,
                file_structure_cache=file_structure_cache,
                source_cache=source_cache,
                severity=severity,
                predicate_registry=predicate_registry,
            )
        )

    return diagnostics


def _to_list(value: str | list[str]) -> list[str]:
    return value if isinstance(value, list) else [value]


def _path_in_scope(*, path: str, target_files: frozenset[str]) -> bool:
    return any(
        path == target or path.startswith(f"{target}/") or target.startswith(f"{path}/")
        for target in target_files
    )


def _paired_file_templates(block: MustBlockV1) -> list[str]:
    templates: list[str] = []
    if block.must is not None and block.must.havePairedFile:
        templates.append(block.must.havePairedFile)
    if block.mustNot is not None and block.mustNot.havePairedFile:
        templates.append(block.mustNot.havePairedFile)
    return templates


def _companion_paths_for_block(
    *,
    block: MustBlockV1,
    parent_context: PredicateContext,
    file_system: FileSystem,
    case_maps: CaseMaps,
) -> list[str]:
    """Resolve every `havePairedFile` companion path implied by `block`.

    Mirrors the real evaluation path in `_evaluate_for_block`: when the
    block has a `for`, its file pattern can capture placeholders (e.g.
    `{adapterName}`) that only exist per-match, not on the convention's
    top-level `paths` match, so the paired-file template must be resolved
    against those nested per-file placeholders rather than the parent's.
    """
    templates = _paired_file_templates(block)
    if not templates:
        return []

    if block.for_ is None:
        return [parent_context.resolve_template(template) for template in templates]

    raw_files = block.for_.files
    file_patterns = raw_files if isinstance(raw_files, list) else [raw_files]
    full_patterns = [
        posixpath.join(parent_context.base_path, parent_context.resolve_template(pattern))
        for pattern in file_patterns
    ]

    matched = _match_with_case_maps(
        patterns=full_patterns,
        file_system=file_system,
        case_maps=case_maps,
    )

    companion_paths: list[str] = []
    for entry in matched:
        merged_placeholders = dict(entry.placeholders)
        merged_placeholders.update(parent_context.placeholders)
        for_context = build_context(
            matched=MatchedPath(path=entry.path, placeholders=merged_placeholders),
            file_system=file_system,
        )
        companion_paths.extend(for_context.resolve_template(template) for template in templates)

    return companion_paths


def _convention_in_scope(
    *,
    matched: list[MatchedPath],
    blocks: list[MustBlockV1],
    static_placeholders: dict[str, PlaceholderValue],
    file_system: FileSystem,
    target_files: frozenset[str],
    case_maps: CaseMaps,
) -> bool:
    # `havePairedFile` is cross-file: whether the anchor file (matched by
    # `convention.paths`) is compliant depends on whether its companion
    # file exists, so editing *only* the companion must still bring this
    # convention into scope -- otherwise a broken pairing produced by
    # deleting/editing just the companion goes unreported under
    # `--files`/`--changed` (see docs/reference/cli.md). This also has to
    # account for `havePairedFile` living inside a nested `for` block,
    # whose file pattern can capture placeholders that don't exist on the
    # convention's top-level match (see `_companion_paths_for_block`).
    has_paired_file_templates = any(_paired_file_templates(block) for block in blocks)

    for entry in matched:
        if _path_in_scope(path=entry.path, target_files=target_files):
            return True

        if not has_paired_file_templates:
            continue

        merged_entry = MatchedPath(
            path=entry.path,
            placeholders={**static_placeholders, **entry.placeholders},
        )
        context = build_context(matched=merged_entry, file_system=file_system)

        for block in blocks:
            companion_paths = _companion_paths_for_block(
                block=block,
                parent_context=context,
                file_system=file_system,
                case_maps=case_maps,
            )
            if any(
                _path_in_scope(path=companion_path, target_files=target_files)
                for companion_path in companion_paths
            ):
                return True

    return False


def _build_case_maps(config: ConfigV1) -> CaseMaps:
    kebab_to_pascal_map = config.kebabToPascalMap
    kebab_to_camel_map = config.kebabToCamelMap
    pascal_to_kebab_map = invert_map(kebab_to_pascal_map)
    camel_to_kebab_map = invert_map(kebab_to_camel_map)
    camel_to_pascal_map = derive_camel_to_pascal_map(
        kebab_to_pascal_map=kebab_to_pascal_map,
        kebab_to_camel_map=kebab_to_camel_map,
    )
    pascal_to_camel_map = invert_map(camel_to_pascal_map)

    return {
        "kebab_to_pascal_map": kebab_to_pascal_map,
        "kebab_to_camel_map": kebab_to_camel_map,
        "pascal_to_kebab_map": pascal_to_kebab_map,
        "camel_to_kebab_map": camel_to_kebab_map,
        "camel_to_pascal_map": camel_to_pascal_map,
        "pascal_to_camel_map": pascal_to_camel_map,
    }


def run(
    *,
    config: ConfigV1,
    file_system: FileSystem,
    predicate_registry: PredicateRegistry | None = None,
    report_suppression_warnings: bool = True,
    target_files: frozenset[str] | None = None,
) -> RunResult:
    registry = predicate_registry or builtin_predicate_registry()
    start_time = time.perf_counter()
    case_maps = _build_case_maps(config)
    checked_paths: set[str] = set()
    diagnostics: list[Diagnostic] = []
    known_rule_names: set[str] = set()
    file_structure_cache: dict[str, PyFileStructure] = {}
    source_cache: dict[str, str] = {}
    unused_files_scanned: set[str] = set()

    for convention in config.conventions:
        matched = _match_with_case_maps(
            patterns=_to_list(convention.paths),
            file_system=file_system,
            case_maps=case_maps,
        )
        blocks = _normalize_must_blocks(
            must=convention.must,
            must_not=convention.mustNot,
            predicate_registry=registry,
        )
        convention_name = convention.name or generate_convention_name(
            must=convention.must,
            must_not=convention.mustNot,
            predicate_registry=registry,
        )
        _add_known_rule_names(
            known_rule_names=known_rule_names,
            convention_name=convention_name,
            blocks=blocks,
        )

        static_placeholders = _build_static_placeholders(
            raw=convention.placeholders,
            case_maps=case_maps,
        )

        # Diff-scoped selection is convention-level: if none of this
        # convention's matched files (or, for `havePairedFile` predicates,
        # their resolved companion paths) are in scope, skip the
        # convention entirely. Otherwise, evaluate its FULL matched set --
        # never narrow to only the in-scope subset, since predicates like
        # `haveType`/`havePairedFile` need the whole convention evaluated
        # to stay correct (see docs/reference/cli.md).
        if target_files is not None and not _convention_in_scope(
            matched=matched,
            blocks=blocks,
            static_placeholders=static_placeholders,
            file_system=file_system,
            target_files=target_files,
            case_maps=case_maps,
        ):
            continue

        severity: DiagnosticSeverity = convention.severity or "error"

        for entry in matched:
            checked_paths.add(entry.path)
            merged_entry = MatchedPath(
                path=entry.path,
                placeholders={**static_placeholders, **entry.placeholders},
            )
            context = build_context(matched=merged_entry, file_system=file_system)

            if _is_file_excluded(
                file_path=entry.path,
                exclude_files=convention.excludeFiles,
                context=context,
            ):
                continue

            for block in blocks:
                if not _evaluate_condition(block=block, context=context):
                    continue

                diagnostics.extend(
                    _with_convention_metadata(
                        _evaluate_for_block(
                            block=block,
                            parent_context=context,
                            file_system=file_system,
                            convention_name=_resolve_block_convention_name(
                                block=block,
                                convention_name=convention_name,
                            ),
                            file_structure_cache=file_structure_cache,
                            source_cache=source_cache,
                            severity=severity,
                            checked_paths=checked_paths,
                            case_maps=case_maps,
                            predicate_registry=registry,
                        ),
                        description=block.description or convention.description,
                        hint=block.hint or convention.hint,
                    )
                )

    if config.unusedCode is not None:
        known_rule_names.add(UNUSED_CONVENTION_NAME)
        unused_result = run_unused_code_with_metadata(
            config=config.unusedCode,
            file_system=file_system,
            source_cache=source_cache,
        )
        # `unusedCode` requires whole-project reference-graph context to
        # classify anything correctly, so under `--files`/`--changed` it
        # is always run -- and reported -- in full. Diff-scoping never
        # narrows unusedCode's diagnostics or files_scanned; doing so
        # silently would hide dead code in files outside the requested
        # scope without any indication that happened. (See
        # docs/reference/cli.md.)
        diagnostics.extend(unused_result.diagnostics)
        unused_files_scanned = unused_result.files_scanned

    suppression_result = _apply_suppressions(
        diagnostics=diagnostics,
        checked_paths=checked_paths,
        unused_files_scanned=unused_files_scanned,
        file_system=file_system,
        source_cache=source_cache,
        known_rule_names=known_rule_names,
        report_hygiene=report_suppression_warnings,
    )

    duration_ms = (time.perf_counter() - start_time) * 1000
    return RunResult(
        diagnostics=[
            *suppression_result.diagnostics,
            *suppression_result.hygiene_diagnostics,
        ],
        suppressed_diagnostics=suppression_result.suppressed,
        files_checked=len(checked_paths),
        duration_ms=duration_ms,
    )


def _add_known_rule_names(
    *,
    known_rule_names: set[str],
    convention_name: str,
    blocks: list[MustBlockV1],
) -> None:
    known_rule_names.add(convention_name)
    for block in blocks:
        known_rule_names.add(
            _resolve_block_convention_name(
                block=block,
                convention_name=convention_name,
            )
        )


def _apply_suppressions(
    *,
    diagnostics: list[Diagnostic],
    checked_paths: set[str],
    unused_files_scanned: set[str],
    file_system: FileSystem,
    source_cache: dict[str, str],
    known_rule_names: set[str],
    report_hygiene: bool,
):
    suppressions_by_file = {}
    parse_diagnostics: list[Diagnostic] = []

    for file_path in _suppression_candidate_files(
        diagnostics=diagnostics,
        checked_paths=checked_paths,
        unused_files_scanned=unused_files_scanned,
        file_system=file_system,
    ):
        source = _try_read_source_with_cache(
            file_path=file_path,
            file_system=file_system,
            source_cache=source_cache,
        )
        if source is None:
            continue

        parse_result = parse_suppressions_for_source(
            file_path=file_path,
            source=source,
        )
        if parse_result.suppressions:
            suppressions_by_file[file_path] = parse_result.suppressions
        parse_diagnostics.extend(parse_result.diagnostics)

    return filter_suppressed_diagnostics(
        diagnostics=diagnostics,
        suppressions_by_file=suppressions_by_file,
        parse_diagnostics=parse_diagnostics,
        known_rule_names=known_rule_names,
        report_hygiene=report_hygiene,
    )


def _suppression_candidate_files(
    *,
    diagnostics: list[Diagnostic],
    checked_paths: set[str],
    unused_files_scanned: set[str],
    file_system: FileSystem,
) -> list[str]:
    candidates = {
        path
        for path in checked_paths
        if _is_readable_file_candidate(path=path, file_system=file_system)
    }
    candidates.update(
        diagnostic.file_path
        for diagnostic in diagnostics
        if _is_readable_file_candidate(path=diagnostic.file_path, file_system=file_system)
    )
    candidates.update(
        path
        for path in unused_files_scanned
        if _is_readable_file_candidate(path=path, file_system=file_system)
    )

    return sorted(candidates)


def _is_readable_file_candidate(*, path: str, file_system: FileSystem) -> bool:
    return file_system.file_exists(path) and not file_system.is_directory(path)


def _read_source_with_cache(
    *,
    file_path: str,
    file_system: FileSystem,
    source_cache: dict[str, str],
) -> str:
    cached = source_cache.get(file_path)
    if cached is not None:
        return cached

    source = file_system.read_file(file_path)
    source_cache[file_path] = source
    return source


def _try_read_source_with_cache(
    *,
    file_path: str,
    file_system: FileSystem,
    source_cache: dict[str, str],
) -> str | None:
    try:
        return _read_source_with_cache(
            file_path=file_path,
            file_system=file_system,
            source_cache=source_cache,
        )
    except OSError:
        return None


__all__ = ["RunResult", "run"]
