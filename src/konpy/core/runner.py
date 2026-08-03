"""Evaluate a resolved `ConfigV1` against a `FileSystem` and return diagnostics.

This module is the public facade over the `run()` implementation. Convention
normalization (name/severity/exclude-files/block-shape resolution) lives in
`core.policy` (shared with `core._explain_model`); the rest of `run()` is
split across the sibling `_runner_*` modules: `_runner_convention_setup`
(diagnostic metadata attachment), `_runner_cross_file` (cross-file index
caching), `_runner_placeholders` (placeholder resolution and
`if`/`excludeFiles` gating), `_runner_predicates` (`must`/`mustNot`
evaluation), `_runner_matching` (path matching, `for` expansion, diff-scope
containment), and `_runner_suppressions` (post-evaluation suppression
filtering).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from konpy.config.schema import ConfigV1
from konpy.core._runner_convention_setup import _with_convention_metadata
from konpy.core._runner_cross_file import RunCrossFileIndexCache
from konpy.core._runner_matching import (
    _block_has_cross_file_predicate,
    _build_case_maps,
    _convention_in_scope,
    _match_with_case_maps,
    _prepare_block_evaluation,
)
from konpy.core._runner_placeholders import (
    _build_static_placeholders,
    _is_file_excluded,
)
from konpy.core._runner_predicates import (
    _check_predicates,
    _resolve_block_convention_name,
)
from konpy.core._runner_suppressions import _add_known_rule_names, _apply_suppressions
from konpy.core.baseline import (
    BaselineData,
    BaselinedDiagnostic,
    BaselineStaleEntry,
    apply_baseline,
)
from konpy.core.context import build_context
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity
from konpy.core.filesystem import FileSystem
from konpy.core.path_matcher import MatchedPath
from konpy.core.policy import resolve_effective_policy
from konpy.core.suppressions import SuppressedDiagnostic
from konpy.predicates.registry import PredicateRegistry, builtin_predicate_registry
from konpy.python_ast.structure import PyFileStructure
from konpy.unused.engine import CONVENTION_NAME as UNUSED_CONVENTION_NAME
from konpy.unused.engine import run_unused_code_with_metadata


@dataclass(frozen=True, kw_only=True)
class RunResult:
    """The outcome of one `run()` pass: diagnostics, counters, and timing."""

    diagnostics: list[Diagnostic]
    files_checked: int
    duration_ms: float | None
    suppressed_diagnostics: list[SuppressedDiagnostic] = field(default_factory=list)
    baselined_diagnostics: list[BaselinedDiagnostic] = field(default_factory=list)
    baseline_stale_entries: list[BaselineStaleEntry] = field(default_factory=list)


def run(
    *,
    config: ConfigV1,
    file_system: FileSystem,
    predicate_registry: PredicateRegistry | None = None,
    report_suppression_warnings: bool = True,
    target_files: frozenset[str] | None = None,
    baseline: BaselineData | None = None,
    run_unused_code: bool = True,
) -> RunResult:
    """Evaluate every convention in `config` against `file_system`.

    Matches each convention's `paths` (and any nested `for` blocks), checks
    its `must`/`mustNot` predicates, runs unused-code detection if
    configured, and applies inline suppressions to the combined
    diagnostics. When `target_files` is given, a convention is skipped
    entirely unless at least one of its matched paths (or, for
    `havePairedFile` predicates, a resolved companion path) falls inside
    that scope -- but a convention that is in scope is still evaluated
    against its full matched set, never a narrowed subset.

    When `baseline` is given, it is applied to whatever diagnostics survive
    suppression filtering (see `core.baseline`): already-recorded violations
    are moved into `RunResult.baselined_diagnostics` instead of
    `RunResult.diagnostics`, and any stale baseline entries are reported via
    `RunResult.baseline_stale_entries`. When `baseline` is `None` (the
    default), both fields stay empty and behavior is unchanged.

    `run_unused_code` (default `True`) gates whether the unused-code engine
    runs at all, even when `config.unusedCode` is set -- it is a whole-project
    scan and by far the most expensive lane, so callers that only care about
    error-severity diagnostics (unused-code findings are warnings by default)
    can set it `False` to skip that cost entirely without changing results.
    """
    registry = predicate_registry or builtin_predicate_registry()
    policy = resolve_effective_policy(config, predicate_registry=registry)
    start_time = time.perf_counter()
    case_maps = _build_case_maps(config)
    checked_paths: set[str] = set()
    diagnostics: list[Diagnostic] = []
    known_rule_names: set[str] = set()
    file_structure_cache: dict[str, PyFileStructure] = {}
    source_cache: dict[str, str] = {}
    cross_file_cache = RunCrossFileIndexCache(
        file_system=file_system,
        file_structure_cache=file_structure_cache,
        source_cache=source_cache,
    )
    unused_files_scanned: set[str] = set()

    for convention in policy.conventions:
        matched = _match_with_case_maps(
            patterns=list(convention.paths),
            file_system=file_system,
            case_maps=case_maps,
        )
        blocks = list(convention.blocks)
        convention_name = convention.name
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
        convention_exclude_files = list(convention.exclude_files)
        if target_files is not None and not _convention_in_scope(
            matched=matched,
            blocks=blocks,
            static_placeholders=static_placeholders,
            convention_exclude_files=convention_exclude_files,
            file_system=file_system,
            target_files=target_files,
            case_maps=case_maps,
            predicate_registry=registry,
        ):
            continue

        severity: DiagnosticSeverity = convention.severity

        parent_contexts = []
        for entry in matched:
            checked_paths.add(entry.path)
            merged_entry = MatchedPath(
                path=entry.path,
                placeholders={**static_placeholders, **entry.placeholders},
            )
            context = build_context(matched=merged_entry, file_system=file_system)

            if _is_file_excluded(
                file_path=entry.path,
                exclude_files=convention_exclude_files,
                context=context,
            ):
                continue

            parent_contexts.append(context)

        prepared_blocks = [
            (
                block,
                _resolve_block_convention_name(
                    block=block,
                    convention_name=convention_name,
                ),
                _prepare_block_evaluation(
                    block=block,
                    parent_contexts=parent_contexts,
                    file_system=file_system,
                    case_maps=case_maps,
                ),
                _block_has_cross_file_predicate(
                    block=block,
                    predicate_registry=registry,
                ),
            )
            for block in blocks
        ]

        for _block, _block_convention_name, prepared, _has_cross_file in prepared_blocks:
            checked_paths.update(prepared.checked_paths)

        for parent_context in parent_contexts:
            for block, block_convention_name, prepared, has_cross_file in prepared_blocks:
                target_contexts = prepared.contexts_by_parent_path.get(
                    parent_context.path,
                    (),
                )
                if not target_contexts:
                    continue

                cross_file_scope = (
                    cross_file_cache.scope(prepared.scope_paths) if has_cross_file else None
                )
                block_diagnostics: list[Diagnostic] = []

                for target_context in target_contexts:
                    block_diagnostics.extend(
                        _check_predicates(
                            must=block.must,
                            must_not=block.mustNot,
                            convention_name=block_convention_name,
                            context=(
                                replace(target_context, cross_file=cross_file_scope)
                                if cross_file_scope is not None
                                else target_context
                            ),
                            file_system=file_system,
                            file_structure_cache=file_structure_cache,
                            source_cache=source_cache,
                            severity=severity,
                            predicate_registry=registry,
                        )
                    )

                diagnostics.extend(
                    _with_convention_metadata(
                        block_diagnostics,
                        description=block.description or convention.description,
                        hint=block.hint or convention.hint,
                    )
                )

    if run_unused_code and policy.unused_code is not None:
        known_rule_names.add(UNUSED_CONVENTION_NAME)
        unused_result = run_unused_code_with_metadata(
            config=policy.unused_code,
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

    remaining_diagnostics = suppression_result.diagnostics
    baselined_diagnostics: list[BaselinedDiagnostic] = []
    baseline_stale_entries: list[BaselineStaleEntry] = []
    if baseline is not None:
        baseline_application = apply_baseline(
            diagnostics=suppression_result.diagnostics,
            baseline=baseline,
        )
        remaining_diagnostics = baseline_application.remaining
        baselined_diagnostics = baseline_application.baselined
        baseline_stale_entries = baseline_application.stale_entries

    duration_ms = (time.perf_counter() - start_time) * 1000
    return RunResult(
        diagnostics=[
            *remaining_diagnostics,
            *suppression_result.hygiene_diagnostics,
        ],
        suppressed_diagnostics=suppression_result.suppressed,
        baselined_diagnostics=baselined_diagnostics,
        baseline_stale_entries=baseline_stale_entries,
        files_checked=len(checked_paths),
        duration_ms=duration_ms,
    )


__all__ = ["RunResult", "run"]
