"""Dataclasses for the zero-config codebase report.

Split out of `konpy.core.report` (which assembles them) to keep that module
under the project's per-module line limit; `report.py` re-exports these names
so the public import path is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from konpy.core._report_tools import ReportToolLane
from konpy.core.diagnostics import Diagnostic


@dataclass(frozen=True, kw_only=True)
class ReportLiteralGroup:
    """One repeated string literal and where it first appears."""

    value: str
    occurrences: int
    first_path: str
    first_line: int
    # Context tag rendered next to the group ("generator template") when every
    # occurrence lives in files that repeat by design rather than by accident.
    label: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReportFunctionGroup:
    """One group of duplicate function implementations."""

    name: str
    statement_count: int
    members: tuple[tuple[str, int], ...]
    label: str | None = None
    # Member names differing from the canonical one — a duplicate hiding
    # behind a rename (`_iter_error_chain` vs `_iter_retry_error_chain`).
    name_variants: tuple[str, ...] = ()
    # True when members span more than one component (a member's component is
    # its first path segment, or its second when the first is `src`/`lib`).
    # Cross-component duplication compounds fastest, so it ranks and renders
    # first.
    is_cross_component: bool = False


@dataclass(frozen=True, kw_only=True)
class ReportCoverage:
    """Docstring and annotation coverage counts over non-test files."""

    module_docs: tuple[int, int]
    class_docs: tuple[int, int]
    function_docs: tuple[int, int]
    annotated_functions: tuple[int, int]


@dataclass(frozen=True, kw_only=True)
class ReportConventions:
    """Summary of the conventions run when a konpy.json is present."""

    status: str
    files_checked: int
    errors: int
    warnings: int
    top_diagnostics: tuple[Diagnostic, ...]
    error_text: str | None


@dataclass(frozen=True, kw_only=True)
class ReportData:
    """Everything the zero-config report renders."""

    files: int
    test_files: int
    generated_files: int
    vendor_files: int
    vendor_roots: tuple[str, ...]
    loc: int
    skipped_unparsable: int
    unused: tuple[Diagnostic, ...]
    literal_groups: tuple[ReportLiteralGroup, ...]
    function_groups: tuple[ReportFunctionGroup, ...]
    tool_lanes: tuple[ReportToolLane, ...]
    coverage: ReportCoverage
    conventions: ReportConventions
    duration_ms: float


__all__ = [
    "ReportConventions",
    "ReportCoverage",
    "ReportData",
    "ReportFunctionGroup",
    "ReportLiteralGroup",
    "ReportToolLane",
]
