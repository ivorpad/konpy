"""`annotate-functions-coverage` heuristic: public functions in a top-level
segment annotate their parameters/return types. Symmetric to
`docstring_coverage`: two independently-thresholded kinds are merged into a
single proposal when at least one clears the threshold.
"""

from __future__ import annotations

from collections.abc import Sequence

from konpy.infer.heuristics import threshold_reason
from konpy.infer.models import HeuristicMineResult, HeuristicSignal, InferFileRecord
from konpy.infer.naming import slugify, top_level_segment

_KIND_LABELS: tuple[str, ...] = ("params", "returns")


def mine(
    records: Sequence[InferFileRecord],
    *,
    min_confidence: float,
    min_support: int,
) -> HeuristicMineResult:
    """Mine per-top-level-segment param/return annotation coverage from `records`."""
    groups: dict[str, list[InferFileRecord]] = {}
    for record in records:
        if record.is_test:
            continue
        groups.setdefault(top_level_segment(record.path), []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for segment in sorted(groups):
        group = groups[segment]
        scope = segment or "."

        included_labels: list[str] = []
        included_support = 0
        included_total = 0
        included_violators: set[str] = set()
        kind_flags: dict[str, bool] = {}
        any_measured = False
        pending_skips: list[HeuristicSignal] = []

        for label in _KIND_LABELS:
            support_k = 0
            total_k = 0
            violators_k: set[str] = set()

            for record in group:
                for function in record.structure.function_annotation_targets:
                    if not function.is_public:
                        continue
                    if label == "params":
                        for param in function.params:
                            total_k += 1
                            if param.type_name is not None:
                                support_k += 1
                            else:
                                violators_k.add(record.path)
                    else:
                        total_k += 1
                        if function.return_type is not None:
                            support_k += 1
                        else:
                            violators_k.add(record.path)

            if total_k == 0:
                kind_flags[label] = False
                continue

            any_measured = True
            reason = threshold_reason(
                support=support_k,
                total=total_k,
                min_confidence=min_confidence,
                min_support=min_support,
            )
            convention_name = f"infer-annotate-functions-coverage-{slugify(segment)}"
            if reason is None:
                kind_flags[label] = True
                included_labels.append(label)
                included_support += support_k
                included_total += total_k
                included_violators.update(violators_k)
            else:
                kind_flags[label] = False
                pending_skips.append(
                    HeuristicSignal(
                        scope=scope,
                        detail=label,
                        support=support_k,
                        total=total_k,
                        violators=[],
                        convention_name=convention_name,
                        convention={},
                        reason=reason,
                    )
                )

        if not any_measured:
            continue

        skipped.extend(pending_skips)

        if not included_labels:
            continue

        detail = ", ".join(included_labels)
        confidence = included_support / included_total
        paths = f"{segment}/**/*.py" if segment else "**/*.py"
        convention_name = f"infer-annotate-functions-coverage-{slugify(segment)}"

        convention = {
            "name": convention_name,
            "description": (
                f'Inferred: {included_support}/{included_total} {detail} in "{scope}" are '
                f"type-annotated ({confidence:.0%} confidence)."
            ),
            "severity": "warning",
            "paths": paths,
            "must": {
                "annotateFunctions": {
                    "returns": kind_flags.get("returns", False),
                    "params": kind_flags.get("params", False),
                    "publicOnly": True,
                }
            },
        }

        proposals.append(
            HeuristicSignal(
                scope=scope,
                detail=detail,
                support=included_support,
                total=included_total,
                violators=sorted(included_violators),
                convention_name=convention_name,
                convention=convention,
            )
        )

    return HeuristicMineResult(proposals=proposals, skipped=skipped)


__all__ = ["mine"]
