"""`import-dominance` heuristic: non-barrel modules in a top-level segment
prefer absolute imports over relative ones. This heuristic only ever
proposes the "prefers absolute" (`mustNot importFromCurrentDir/Parents`)
direction — it has no code path that proposes the reverse.
"""

from __future__ import annotations

from collections.abc import Sequence

from konsistent.infer.heuristics import classify_signal
from konsistent.infer.models import HeuristicMineResult, HeuristicSignal, InferFileRecord
from konsistent.infer.naming import slugify, top_level_segment


def mine(
    records: Sequence[InferFileRecord],
    *,
    min_confidence: float,
    min_support: int,
) -> HeuristicMineResult:
    groups: dict[str, list[InferFileRecord]] = {}
    for record in records:
        if record.is_test or record.is_init:
            continue
        groups.setdefault(top_level_segment(record.path), []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for segment in sorted(groups):
        counted: list[InferFileRecord] = []
        relative: list[InferFileRecord] = []

        for record in groups[segment]:
            has_any_import = any(
                not source.is_type for source in record.structure.import_sources
            )
            if not has_any_import:
                continue
            counted.append(record)
            has_relative = any(
                source.level >= 1 and not source.is_type
                for source in record.structure.import_sources
            )
            if has_relative:
                relative.append(record)

        total = len(counted)
        if total == 0:
            continue

        support = total - len(relative)
        violators = sorted(record.path for record in relative)
        confidence = support / total
        scope = segment or "."
        if segment:
            paths = [f"{segment}/**/*.py", f"!{segment}/**/__init__.py"]
        else:
            paths = ["**/*.py", "!**/__init__.py"]
        convention_name = f"infer-import-dominance-{slugify(segment)}"

        convention = {
            "name": convention_name,
            "description": (
                f'Inferred: {support}/{total} files in "{scope}" prefer absolute imports '
                f"over relative imports ({confidence:.0%} confidence)."
            ),
            "severity": "warning",
            "paths": paths,
            "mustNot": {"importFromCurrentDir": True, "importFromParents": True},
        }

        signal = HeuristicSignal(
            scope=scope,
            detail=None,
            support=support,
            total=total,
            violators=violators,
            convention_name=convention_name,
            convention=convention,
        )

        proposal, skip = classify_signal(
            signal,
            min_confidence=min_confidence,
            min_support=min_support,
        )
        if proposal is not None:
            proposals.append(proposal)
        if skip is not None:
            skipped.append(skip)

    return HeuristicMineResult(proposals=proposals, skipped=skipped)


__all__ = ["mine"]
