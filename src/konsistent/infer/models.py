"""Data models for `konsistent infer` (M15 convention mining).

These dataclasses are entirely separate from ``config/schema.py`` — no
confidence/support/violator metadata ever leaks into the
``ReusableConventionsPackageV1`` grammar that proposed conventions are
validated against. See ``docs/guides/inferring-conventions.md`` for the
user-facing contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from konsistent.python_ast.structure import PyFileStructure


@dataclass(frozen=True, kw_only=True)
class InferFileRecord:
    """One successfully-parsed Python file considered by the miner."""

    path: str
    directory: str
    stem: str
    is_test: bool
    is_init: bool
    structure: PyFileStructure


@dataclass(frozen=True, kw_only=True)
class HeuristicSignal:
    """Internal, per-scope unit produced by one ``heuristics/*.py`` module."""

    scope: str
    detail: str | None
    support: int
    total: int
    violators: list[str]
    convention_name: str
    convention: dict[str, Any]
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class HeuristicMineResult:
    proposals: list[HeuristicSignal]
    skipped: list[HeuristicSignal]


@dataclass(frozen=True, kw_only=True)
class InferProposal:
    heuristic: str
    convention_name: str
    scope: str
    detail: str | None
    support: int
    total: int
    confidence: float
    violators: list[str]
    omitted_violators: int
    convention: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class InferSkipped:
    heuristic: str
    scope: str
    detail: str | None
    support: int
    total: int
    confidence: float
    reason: str


@dataclass(frozen=True, kw_only=True)
class InferReport:
    files_scanned: int
    test_files_excluded: int
    files_skipped_unparsable: int
    files_skipped_unreadable: int
    proposals: list[InferProposal]
    skipped: list[InferSkipped]


__all__ = [
    "HeuristicMineResult",
    "HeuristicSignal",
    "InferFileRecord",
    "InferProposal",
    "InferReport",
    "InferSkipped",
]
