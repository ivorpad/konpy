from __future__ import annotations

from dataclasses import dataclass

from konsistent.core.diagnostics import Diagnostic


@dataclass(frozen=True, kw_only=True)
class TruncateResult:
    diagnostics: list[Diagnostic]
    omitted: int


def truncate_diagnostics(*, diagnostics: list[Diagnostic], max: int) -> TruncateResult:
    if len(diagnostics) <= max:
        return TruncateResult(diagnostics=diagnostics, omitted=0)
    return TruncateResult(diagnostics=diagnostics[:max], omitted=len(diagnostics) - max)


def format_truncation_message(omitted: int) -> str:
    return f"... and {omitted} more diagnostics (use --max-diagnostics to see more)"


__all__ = ["TruncateResult", "format_truncation_message", "truncate_diagnostics"]
