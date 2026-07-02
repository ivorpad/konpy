"""`barrel-usage` heuristic: `__init__.py` files in a top-level segment
contain only barrel statements (docstring/imports/`__all__`/re-exports).
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
        if not record.is_init:
            continue
        groups.setdefault(top_level_segment(record.path), []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for segment in sorted(groups):
        group = groups[segment]

        violators = sorted(
            record.path for record in group if record.structure.non_barrel_statements
        )
        support = len(group) - len(violators)
        total = len(group)
        confidence = support / total
        scope = segment or "."
        paths = f"{segment}/**/__init__.py" if segment else "**/__init__.py"
        convention_name = f"infer-barrel-usage-{slugify(segment)}"

        convention = {
            "name": convention_name,
            "description": (
                f'Inferred: {support}/{total} __init__.py files in "{scope}" are pure '
                f"barrel files ({confidence:.0%} confidence)."
            ),
            "severity": "warning",
            "paths": paths,
            "must": {"areBarrelFiles": True},
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
