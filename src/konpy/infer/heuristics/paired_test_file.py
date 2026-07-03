"""`paired-test-file` heuristic: production modules in a directory have a
matching `test_<name>.py`/`<name>_test.py` file. Grouping key: exact
directory (direct children only).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from konpy.infer.heuristics import classify_signal
from konpy.infer.models import HeuristicMineResult, HeuristicSignal, InferFileRecord
from konpy.infer.naming import slugify


def _templates_for(record: InferFileRecord) -> tuple[str, str] | None:
    stem = record.stem
    if stem.startswith("test_") and len(stem) > 5:
        normalized = stem[5:]
        template = (
            f"{record.directory}/test_${{name}}.py" if record.directory else "test_${name}.py"
        )
        return normalized, template
    if stem.endswith("_test") and len(stem) > 5:
        normalized = stem[:-5]
        template = (
            f"{record.directory}/${{name}}_test.py" if record.directory else "${name}_test.py"
        )
        return normalized, template
    return None


def mine(
    records: Sequence[InferFileRecord],
    *,
    min_confidence: float,
    min_support: int,
) -> HeuristicMineResult:
    """Mine per-directory production-module-has-a-paired-test-file coverage from `records`."""
    test_index: dict[str, list[str]] = {}
    for record in records:
        if not record.is_test:
            continue
        result = _templates_for(record)
        if result is None:
            continue
        normalized, template = result
        test_index.setdefault(normalized, []).append(template)

    groups: dict[str, list[InferFileRecord]] = {}
    for record in records:
        if record.is_test or record.is_init:
            continue
        groups.setdefault(record.directory, []).append(record)

    proposals: list[HeuristicSignal] = []
    skipped: list[HeuristicSignal] = []

    for directory in sorted(groups):
        group = groups[directory]

        template_counter: Counter[str] = Counter()
        for record in group:
            for template in test_index.get(record.stem, []):
                template_counter[template] += 1

        if not template_counter:
            continue

        winning_template = min(template_counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        support = template_counter[winning_template]
        total = len(group)
        violators = sorted(
            record.path
            for record in group
            if winning_template not in test_index.get(record.stem, [])
        )

        scope = directory or "."
        if directory:
            paths = [f"{directory}/{{name}}.py", f"!{directory}/__init__.py"]
        else:
            paths = ["{name}.py", "!__init__.py"]
        convention_name = f"infer-paired-test-file-{slugify(directory)}"
        confidence = support / total

        convention = {
            "name": convention_name,
            "description": (
                f'Inferred: {support}/{total} files in "{scope}" have a paired test at '
                f'"{winning_template}" ({confidence:.0%} confidence).'
            ),
            "severity": "warning",
            "paths": paths,
            "must": {"havePairedFile": winning_template},
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
