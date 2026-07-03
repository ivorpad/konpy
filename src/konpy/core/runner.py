"""Evaluate a resolved `ConfigV1` against a `FileSystem` and return diagnostics.

This module is the public facade over the `run()` implementation, which is
split across the sibling `_runner_*` modules: `_runner_types` (shared small
types), `_runner_source_cache` (cached source/AST reads), `_runner_placeholders`
(placeholder resolution and `if`/`excludeFiles` gating), `_runner_messages`
(forbidden-predicate names and messages), `_runner_fix_data` (`mustNot` fix
data), `_runner_predicates` (`must`/`mustNot` evaluation), `_runner_matching`
(path matching, `for` expansion, diff-scope containment), and
`_runner_suppressions` (post-evaluation suppression filtering).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from konpy.config.schema import ConfigV1
from konpy.core._runner_convention_setup import (
    _normalize_must_blocks,
    _with_convention_metadata,
)
from konpy.core._runner_matching import (
    _build_case_maps,
    _convention_in_scope,
    _evaluate_for_block,
    _match_with_case_maps,
    _to_list,
)
from konpy.core._runner_placeholders import (
    _build_static_placeholders,
    _evaluate_condition,
    _is_file_excluded,
)
from konpy.core._runner_predicates import _resolve_block_convention_name
from konpy.core._runner_suppressions import _add_known_rule_names, _apply_suppressions
from konpy.core.context import build_context
from konpy.core.convention_name import generate_convention_name
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity
from konpy.core.filesystem import FileSystem
from konpy.core.path_matcher import MatchedPath
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


def run(
    *,
    config: ConfigV1,
    file_system: FileSystem,
    predicate_registry: PredicateRegistry | None = None,
    report_suppression_warnings: bool = True,
    target_files: frozenset[str] | None = None,
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
    """
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


__all__ = ["RunResult", "run"]
