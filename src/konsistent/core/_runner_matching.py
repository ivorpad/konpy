"""Path matching, `for` expansion, and diff-scope containment checks."""

from __future__ import annotations

import posixpath

from konsistent.config.schema import ConfigV1, MustBlockV1
from konsistent.core._runner_placeholders import _is_file_excluded
from konsistent.core._runner_predicates import _check_predicates
from konsistent.core._runner_types import CaseMaps
from konsistent.core.case_utils import derive_camel_to_pascal_map, invert_map
from konsistent.core.context import PredicateContext, build_context
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity
from konsistent.core.filesystem import FileSystem
from konsistent.core.path_matcher import MatchedPath, match_paths
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.registry import PredicateRegistry
from konsistent.python_ast.structure import PyFileStructure


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
