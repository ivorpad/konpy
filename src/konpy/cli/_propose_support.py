"""Aggregation helpers for `konpy hook-propose`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from konpy.cli._hook_findings import HookFinding


@dataclass(frozen=True)
class AggregatedFinding:
    """Hook fail findings grouped by exact verification prompt."""

    prompt: str
    agent: str
    occurrences: int
    file_paths: tuple[str, ...]
    reasons: tuple[str, ...]


def aggregate_findings(
    findings: Sequence[HookFinding],
    *,
    max_files: int = 10,
    max_reasons: int = 5,
) -> list[AggregatedFinding]:
    """Group findings by exact prompt, preserving first-seen evidence order."""
    grouped: dict[str, list[HookFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.prompt, []).append(finding)

    aggregated: list[AggregatedFinding] = []
    for prompt, group in grouped.items():
        file_paths = _dedupe_preserving_order(finding.filePath for finding in group)
        reasons = _dedupe_preserving_order(
            reason for finding in group for reason in finding.reasons
        )
        aggregated.append(
            AggregatedFinding(
                prompt=prompt,
                agent=group[0].agent,
                occurrences=len(group),
                file_paths=tuple(file_paths[:max_files]),
                reasons=tuple(reasons[:max_reasons]),
            )
        )

    return sorted(aggregated, key=lambda item: (-item.occurrences, item.prompt))


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


__all__ = ["AggregatedFinding", "aggregate_findings"]
