"""Data models for `konpy infer` (M15 convention mining).

These dataclasses are entirely separate from ``config/schema.py`` — no
confidence/support/violator metadata ever leaks into the
``ReusableConventionsPackageV1`` grammar that proposed conventions are
validated against. See ``docs/guides/inferring-conventions.md`` for the
user-facing contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from konpy.python_ast.structure import PyFileStructure


@dataclass(frozen=True, kw_only=True)
class InferFileRecord:
    """One successfully-parsed Python file considered by the miner."""

    path: str
    directory: str
    stem: str
    is_test: bool
    is_init: bool
    structure: PyFileStructure
    # Physical line count, for the file-length ratchet heuristic.
    line_count: int = 0


@dataclass(frozen=True, kw_only=True)
class HeuristicSignal:
    """Internal, per-scope unit produced by one ``heuristics/*.py`` module."""

    scope: str
    detail: str | None
    support: int
    total: int
    violators: list[str]
    convention_name: str
    convention: dict[str, object]
    reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class HeuristicMineResult:
    """The proposal and skipped signals produced by one heuristic's `mine`."""

    proposals: list[HeuristicSignal]
    skipped: list[HeuristicSignal]


@dataclass(frozen=True, kw_only=True)
class InferProposal:
    """A scored, ready-to-render convention proposal for `konpy infer`."""

    heuristic: str
    convention_name: str
    scope: str
    detail: str | None
    support: int
    total: int
    confidence: float
    violators: list[str]
    omitted_violators: int
    convention: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class InferSkipped:
    """A heuristic signal that did not meet the threshold to become a proposal."""

    heuristic: str
    scope: str
    detail: str | None
    support: int
    total: int
    confidence: float
    reason: str


@dataclass(frozen=True, kw_only=True)
class InferReport:
    """The full `konpy infer` output: scan stats, proposals, and skipped signals."""

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
