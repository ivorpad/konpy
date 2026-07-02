from __future__ import annotations

import posixpath
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

        severity: DiagnosticSeverity = convention.severity or "error"
        static_placeholders = _build_static_placeholders(
            raw=convention.placeholders,
            case_maps=case_maps,
        )

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
