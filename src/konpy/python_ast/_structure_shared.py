from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class SourcePosition:
    """A 1-based line/column location in a source file."""

    column: int
    line: int


__all__: list[str] = []
