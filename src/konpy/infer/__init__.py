"""`konpy infer` — mine an existing repo for candidate structural
conventions (M15). Read-only, deterministic, no existing-config awareness.
See ``docs/guides/inferring-conventions.md``.
"""

from __future__ import annotations

from konpy.infer.engine import (
    DEFAULT_MAX_VIOLATORS,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_SUPPORT,
    HEURISTIC_NAMES,
    build_pack,
    run_infer,
)
from konpy.infer.models import (
    HeuristicMineResult,
    HeuristicSignal,
    InferFileRecord,
    InferProposal,
    InferReport,
    InferSkipped,
)
from konpy.infer.report import render_report_json, render_report_markdown, render_report_text

__all__ = [
    "DEFAULT_MAX_VIOLATORS",
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_MIN_SUPPORT",
    "HEURISTIC_NAMES",
    "HeuristicMineResult",
    "HeuristicSignal",
    "InferFileRecord",
    "InferProposal",
    "InferReport",
    "InferSkipped",
    "build_pack",
    "render_report_json",
    "render_report_markdown",
    "render_report_text",
    "run_infer",
]
