"""`file-length` heuristic: propose a line-count ratchet only for clean scopes."""

from __future__ import annotations

from collections.abc import Sequence

from konpy.infer.heuristics import BELOW_MIN_SUPPORT
from konpy.infer.models import HeuristicMineResult, HeuristicSignal, InferFileRecord
from konpy.infer.naming import slugify, top_level_segment
from konpy.predicates.restrict_file_length import DEFAULT_MAX_LINES

_EXISTING_VIOLATIONS = "existing-violations"


def mine(
    records: Sequence[InferFileRecord],
    *,
    min_confidence: float,
    min_support: int,
) -> HeuristicMineResult:
    """Mine clean-only file-length ratchets by top-level segment."""
    del min_confidence

    groups: dict[str, list[InferFileRecord]] = {}
    for record in records:
        if record.is_test:
            continue
        groups.setdefault(top_level_segment(record.path), []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for segment in sorted(groups):
        group = groups[segment]
        total = len(group)
        convention_name = f"infer-file-length-{slugify(segment)}"

        if total < min_support:
            skipped.append(
                _signal(
                    segment=segment,
                    convention_name=convention_name,
                    support=total,
                    total=total,
                    convention={},
                    violators=[],
                    reason=BELOW_MIN_SUPPORT,
                )
            )
            continue

        violators = sorted(
            record.path for record in group if record.line_count > DEFAULT_MAX_LINES
        )
        if violators:
            skipped.append(
                _signal(
                    segment=segment,
                    convention_name=convention_name,
                    support=max(0, total - len(violators)),
                    total=total,
                    convention={},
                    violators=violators,
                    reason=_EXISTING_VIOLATIONS,
                )
            )
            continue

        proposals.append(
            _signal(
                segment=segment,
                convention_name=convention_name,
                support=total,
                total=total,
                convention=_convention(segment=segment, convention_name=convention_name),
                violators=[],
                reason=None,
            )
        )

    return HeuristicMineResult(proposals=proposals, skipped=skipped)


def _signal(
    *,
    segment: str,
    convention_name: str,
    support: int,
    total: int,
    convention: dict[str, object],
    violators: list[str],
    reason: str | None,
) -> HeuristicSignal:
    return HeuristicSignal(
        scope=segment or ".",
        detail=None,
        support=support,
        total=total,
        violators=violators,
        convention_name=convention_name,
        convention=convention,
        reason=reason,
    )


def _convention(*, segment: str, convention_name: str) -> dict[str, object]:
    scope = segment or "."
    paths = f"{segment}/**/*.py" if segment else "**/*.py"
    return {
        "name": convention_name,
        "description": (
            f'Inferred: every file in "{scope}" currently fits within '
            f"{DEFAULT_MAX_LINES} lines."
        ),
        "severity": "warning",
        "paths": paths,
        "must": {"restrictFileLength": True},
    }


__all__ = ["mine"]
