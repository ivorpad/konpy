from __future__ import annotations

import math


def format_time(ms: float) -> str:
    if ms < 1000:
        return f"{math.floor(ms + 0.5)}ms"
    return f"{ms / 1000:.1f}s"


__all__ = ["format_time"]
