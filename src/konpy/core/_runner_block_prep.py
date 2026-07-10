"""Prepare convention must-block target contexts and effective cross-file scopes."""

from __future__ import annotations

import posixpath
from collections.abc import Sequence
from dataclasses import dataclass

from konpy.config.schema import MustBlockV1
from konpy.core._runner_placeholders import _evaluate_condition, _is_file_excluded
from konpy.core._runner_types import CaseMaps
from konpy.core.context import PredicateContext, build_context
from konpy.core.filesystem import FileSystem
from konpy.core.path_matcher import MatchedPath, match_paths


@dataclass(frozen=True, kw_only=True)
class _PreparedBlockEvaluation:
    contexts_by_parent_path: dict[str, tuple[PredicateContext, ...]]
    scope_paths: tuple[str, ...]
    checked_paths: tuple[str, ...]


def _prepare_block_evaluation(
    *,
    block: MustBlockV1,
    parent_contexts: Sequence[PredicateContext],
    file_system: FileSystem,
    case_maps: CaseMaps,
) -> _PreparedBlockEvaluation:
    contexts_by_parent_path: dict[str, tuple[PredicateContext, ...]] = {}
    scope_paths: list[str] = []
    checked_paths: list[str] = []

    for parent_context in parent_contexts:
        if not _evaluate_condition(block=block, context=parent_context):
            contexts_by_parent_path[parent_context.path] = ()
            continue

        target_contexts, target_checked_paths = _target_contexts_for_block(
            block=block,
            parent_context=parent_context,
            file_system=file_system,
            case_maps=case_maps,
        )
        checked_paths.extend(target_checked_paths)

        filtered_contexts = tuple(
            target_context
            for target_context in target_contexts
            if not _is_file_excluded(
                file_path=target_context.path,
                exclude_files=block.excludeFiles,
                context=target_context,
            )
        )
        contexts_by_parent_path[parent_context.path] = filtered_contexts
        scope_paths.extend(target_context.path for target_context in filtered_contexts)

    return _PreparedBlockEvaluation(
        contexts_by_parent_path=contexts_by_parent_path,
        scope_paths=tuple(sorted(set(scope_paths))),
        checked_paths=tuple(sorted(set(checked_paths))),
    )


def _target_contexts_for_block(
    *,
    block: MustBlockV1,
    parent_context: PredicateContext,
    file_system: FileSystem,
    case_maps: CaseMaps,
) -> tuple[tuple[PredicateContext, ...], tuple[str, ...]]:
    if block.for_ is None:
        return (parent_context,), ()

    raw_files = block.for_.files
    file_patterns = raw_files if isinstance(raw_files, list) else [raw_files]
    full_patterns = [
        posixpath.join(parent_context.base_path, parent_context.resolve_template(pattern))
        for pattern in file_patterns
    ]

    matched = _match_with_case_maps_for_block_prep(
        patterns=full_patterns,
        file_system=file_system,
        case_maps=case_maps,
    )

    contexts: list[PredicateContext] = []
    checked_paths: list[str] = []

    for entry in matched:
        checked_paths.append(entry.path)
        merged_placeholders = dict(entry.placeholders)
        merged_placeholders.update(parent_context.placeholders)
        contexts.append(
            build_context(
                matched=MatchedPath(
                    path=entry.path,
                    placeholders=merged_placeholders,
                ),
                file_system=file_system,
            )
        )

    return tuple(contexts), tuple(checked_paths)


def _match_with_case_maps_for_block_prep(
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


__all__: list[str] = []
