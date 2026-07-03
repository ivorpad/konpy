"""Shared support/confidence threshold logic for `konpy infer` heuristics."""

from __future__ import annotations

from dataclasses import replace

from konpy.infer.models import HeuristicSignal

BELOW_MIN_SUPPORT = "below-min-support"
BELOW_MIN_CONFIDENCE = "below-min-confidence"


def threshold_reason(
    *,
    support: int,
    total: int,
    min_confidence: float,
    min_support: int,
) -> str | None:
    """Shared per-signal threshold logic (`>=` inclusive at both boundaries)."""

    if total < min_support:
        return BELOW_MIN_SUPPORT
    if support / total < min_confidence:
        return BELOW_MIN_CONFIDENCE
    return None


def classify_signal(
    signal: HeuristicSignal,
    *,
    min_confidence: float,
    min_support: int,
) -> tuple[HeuristicSignal | None, HeuristicSignal | None]:
    """Returns ``(proposal, skipped)`` — exactly one of the two is not ``None``."""

    reason = threshold_reason(
        support=signal.support,
        total=signal.total,
        min_confidence=min_confidence,
        min_support=min_support,
    )
    if reason is None:
        return signal, None
    return None, replace(signal, reason=reason)
