"""Naming helpers for `konsistent infer` convention/scope names."""

from __future__ import annotations

import re

_SLUG_INVALID = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    lowered = text.strip("/").lower()
    collapsed = _SLUG_INVALID.sub("-", lowered)
    stripped = collapsed.strip("-")
    return stripped or "root"


def top_level_segment(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


__all__ = ["slugify", "top_level_segment"]
