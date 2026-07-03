"""`export-suffix` heuristic: `{name}_<suffix>.py` files export a matching
`{Name}<Suffix>` class. Grouping key: exact directory + suffix token.
"""

from __future__ import annotations

from collections.abc import Sequence

from konpy.core.case_utils import to_pascal_case
from konpy.infer.heuristics import classify_signal
from konpy.infer.models import HeuristicMineResult, HeuristicSignal, InferFileRecord
from konpy.infer.naming import slugify

KNOWN_EXPORT_SUFFIXES: tuple[str, ...] = (
    "Service",
    "Adapter",
    "Repository",
    "Handler",
    "Manager",
    "Controller",
    "Factory",
    "Builder",
    "Client",
    "Provider",
    "Gateway",
    "Validator",
    "Serializer",
    "Middleware",
    "Strategy",
    "Worker",
    "Resolver",
)

_SUFFIX_BY_LOWER: dict[str, str] = {suffix.lower(): suffix for suffix in KNOWN_EXPORT_SUFFIXES}


def mine(
    records: Sequence[InferFileRecord],
    *,
    min_confidence: float,
    min_support: int,
) -> HeuristicMineResult:
    """Mine per-directory-and-suffix export-name-matches-filename coverage from `records`."""
    groups: dict[tuple[str, str], list[InferFileRecord]] = {}

    for record in records:
        if record.is_test or record.is_init:
            continue
        tokens = record.stem.split("_")
        if len(tokens) < 2:
            continue
        suffix_token = tokens[-1].lower()
        if suffix_token not in _SUFFIX_BY_LOWER:
            continue
        groups.setdefault((record.directory, suffix_token), []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for directory, suffix_token in sorted(groups):
        group = groups[(directory, suffix_token)]
        suffix_pascal = _SUFFIX_BY_LOWER[suffix_token]

        violators: list[str] = []
        support = 0
        for record in group:
            name_part = record.stem[: -(len(suffix_token) + 1)]
            expected_class = to_pascal_case(name_part) + suffix_pascal
            is_matched = any(
                export.name == expected_class and export.kind in {"class", "re-export"}
                for export in record.structure.exports
            )
            if is_matched:
                support += 1
            else:
                violators.append(record.path)

        violators.sort()
        total = len(group)
        confidence = support / total
        scope = directory or "."
        path_prefix = f"{directory}/" if directory else ""
        paths = f"{path_prefix}{{name}}_{suffix_token}.py"
        convention_name = f"infer-export-suffix-{slugify(directory)}-{suffix_token}"

        convention = {
            "name": convention_name,
            "description": (
                f'Inferred: {support}/{total} files in "{scope}" matching '
                f"*_{suffix_token}.py export a `{{name}}{suffix_pascal}` class "
                f"({confidence:.0%} confidence)."
            ),
            "severity": "warning",
            "paths": paths,
            "must": {"exportClasses": [f"${{name.toPascalCase()}}{suffix_pascal}"]},
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


__all__ = ["KNOWN_EXPORT_SUFFIXES", "mine"]
