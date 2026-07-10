"""Engine orchestration for `konpy infer` (M15 convention mining).

Resolves scan defaults, runs the requested heuristics in a fixed declared
order, deduplicates convention names, applies `--max-violators` truncation,
and assembles the final `InferReport`. Also builds the
`ReusableConventionsPackageV1`-shaped proposed-pack dict (the primary CLI
artifact) — the same reviewable-pack contract `extract-rules` emits, never
a `RawConfigV1`/`konpy.json`-shaped document.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from konpy.core.filesystem import FileSystem
from konpy.infer.heuristics import (
    annotate_coverage,
    barrel_usage,
    docstring_coverage,
    duplicate_functions,
    export_suffix,
    import_dominance,
    paired_test_file,
    repeated_literals,
)
from konpy.infer.models import InferProposal, InferReport, InferSkipped
from konpy.infer.scan import collect_file_records
from konpy.unused.engine import DEFAULT_INCLUDE as DEFAULT_INFER_INCLUDE
from konpy.unused.engine import DEFAULT_TEST_GLOBS as DEFAULT_INFER_TEST_GLOBS

HEURISTIC_NAMES: tuple[str, ...] = (
    "export-suffix",
    "paired-test-file",
    "docstring-coverage",
    "annotate-functions-coverage",
    "barrel-usage",
    "import-dominance",
    "repeated-literals",
    "duplicate-functions",
)

DEFAULT_MIN_CONFIDENCE = 0.9
DEFAULT_MIN_SUPPORT = 3
DEFAULT_MAX_VIOLATORS = 10

_MINERS = {
    "export-suffix": export_suffix.mine,
    "paired-test-file": paired_test_file.mine,
    "docstring-coverage": docstring_coverage.mine,
    "annotate-functions-coverage": annotate_coverage.mine,
    "barrel-usage": barrel_usage.mine,
    "import-dominance": import_dominance.mine,
    "repeated-literals": repeated_literals.mine,
    "duplicate-functions": duplicate_functions.mine,
}


def run_infer(
    *,
    file_system: FileSystem,
    include: Sequence[str] = DEFAULT_INFER_INCLUDE,
    exclude: Sequence[str] = (),
    test_globs: Sequence[str] = DEFAULT_INFER_TEST_GLOBS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_support: int = DEFAULT_MIN_SUPPORT,
    max_violators: int = DEFAULT_MAX_VIOLATORS,
    heuristics: Sequence[str] | None = None,
) -> InferReport:
    """Mine `file_system` for structural conventions and return a scored report."""
    records, unparsable, unreadable = collect_file_records(
        file_system=file_system,
        include=include,
        exclude=exclude,
        test_globs=test_globs,
    )

    selected = set(heuristics) if heuristics else set(HEURISTIC_NAMES)

    proposals: list[InferProposal] = []
    skipped: list[InferSkipped] = []
    seen_names: dict[str, int] = {}

    for heuristic_name in HEURISTIC_NAMES:
        if heuristic_name not in selected:
            continue

        result = _MINERS[heuristic_name](
            records,
            min_confidence=min_confidence,
            min_support=min_support,
        )

        for signal in result.proposals:
            count = seen_names.get(signal.convention_name, 0) + 1
            seen_names[signal.convention_name] = count
            final_name = (
                signal.convention_name if count == 1 else f"{signal.convention_name}-{count}"
            )
            convention = dict(signal.convention)
            convention["name"] = final_name

            truncated_violators = signal.violators[:max_violators]
            omitted = max(0, len(signal.violators) - max_violators)

            proposals.append(
                InferProposal(
                    heuristic=heuristic_name,
                    convention_name=final_name,
                    scope=signal.scope,
                    detail=signal.detail,
                    support=signal.support,
                    total=signal.total,
                    confidence=signal.support / signal.total,
                    violators=truncated_violators,
                    omitted_violators=omitted,
                    convention=convention,
                )
            )

        for signal in result.skipped:
            skipped.append(
                InferSkipped(
                    heuristic=heuristic_name,
                    scope=signal.scope,
                    detail=signal.detail,
                    support=signal.support,
                    total=signal.total,
                    confidence=signal.support / signal.total,
                    reason=signal.reason or "below-min-confidence",
                )
            )

    return InferReport(
        files_scanned=len(records),
        test_files_excluded=sum(1 for record in records if record.is_test),
        files_skipped_unparsable=unparsable,
        files_skipped_unreadable=unreadable,
        proposals=proposals,
        skipped=skipped,
    )


def build_pack(report: InferReport) -> dict[str, Any]:
    """Build the `ReusableConventionsPackageV1`-shaped proposed pack.

    Deliberately mirrors `extract-rules`' output contract (see
    `konpy.cli.extract_rules`), never the `RawConfigV1`/`konpy.json`
    shape — an inferred proposal is a human-review artifact, not something
    that could be mistaken for (or accidentally used as) a real config.
    """
    return {
        "conventionSpecVersion": "v1",
        "conventions": [proposal.convention for proposal in report.proposals],
    }


__all__ = [
    "DEFAULT_INFER_INCLUDE",
    "DEFAULT_INFER_TEST_GLOBS",
    "DEFAULT_MAX_VIOLATORS",
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_MIN_SUPPORT",
    "HEURISTIC_NAMES",
    "build_pack",
    "run_infer",
]
