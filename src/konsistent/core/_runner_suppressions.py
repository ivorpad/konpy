"""Post-evaluation suppression filtering for a completed `run()` pass."""

from __future__ import annotations

from konsistent.config.schema import MustBlockV1
from konsistent.core._runner_predicates import _resolve_block_convention_name
from konsistent.core._runner_source_cache import _try_read_source_with_cache
from konsistent.core.diagnostics import Diagnostic
from konsistent.core.filesystem import FileSystem
from konsistent.core.suppressions import (
    SuppressionComment,
    SuppressionFilterResult,
    filter_suppressed_diagnostics,
    parse_suppressions_for_source,
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


def _is_readable_file_candidate(*, path: str, file_system: FileSystem) -> bool:
    return file_system.file_exists(path) and not file_system.is_directory(path)


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


def _apply_suppressions(
    *,
    diagnostics: list[Diagnostic],
    checked_paths: set[str],
    unused_files_scanned: set[str],
    file_system: FileSystem,
    source_cache: dict[str, str],
    known_rule_names: set[str],
    report_hygiene: bool,
) -> SuppressionFilterResult:
    """Parse inline suppression comments and filter the diagnostics they cover.

    Returns the `SuppressionFilterResult` describing the surviving
    diagnostics, the suppressed ones, and any hygiene diagnostics
    (stale/unknown suppressions), unless `report_hygiene` is `False`.
    """
    suppressions_by_file: dict[str, list[SuppressionComment]] = {}
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
