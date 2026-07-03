"""Heuristic modules for `konsistent infer` (M15 convention mining).

Each module exports exactly one ``mine()`` function taking a sequence of
``InferFileRecord`` plus ``min_confidence``/``min_support`` thresholds, and
returning a ``HeuristicMineResult``.
"""

from konsistent.infer.heuristics._thresholds import (
    BELOW_MIN_CONFIDENCE,
    BELOW_MIN_SUPPORT,
    classify_signal,
    threshold_reason,
)

__all__ = [
    "BELOW_MIN_CONFIDENCE",
    "BELOW_MIN_SUPPORT",
    "classify_signal",
    "threshold_reason",
]
