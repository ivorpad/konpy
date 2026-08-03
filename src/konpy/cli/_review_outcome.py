"""Structured review outcomes for the agentic `konpy hook` verifier.

Design rule: review meaning lives in a `ReviewOutcome`, never in a process
exit code. Verification helpers in this package return a `ReviewOutcome`;
only their callers (e.g. `konpy hook`) map that outcome onto an exit code,
each caller free to choose its own mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReviewStatus = Literal["pass", "findings", "unavailable", "invalid-response"]
"""Overall verdict of a review run.

- "pass": every verified path passed.
- "findings": at least one path had a verified fail verdict.
- "unavailable": the verifier agent could not run or exited nonzero for at
  least one path (and no path produced findings).
- "invalid-response": the verifier agent ran but returned no valid verdict
  for at least one path (and no path produced findings).
"""


@dataclass(frozen=True, kw_only=True)
class ReviewFinding:
    """A single verified fail verdict for one path, optionally rule-scoped."""

    path: str
    rule: str | None = None
    reasons: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ReviewOutcome:
    """The combined result of running one or more verifications."""

    status: ReviewStatus
    findings: tuple[ReviewFinding, ...] = ()
    warnings: tuple[str, ...] = ()


def combined_review_status(
    *,
    has_findings: bool,
    saw_invalid_response: bool,
    saw_unavailable: bool,
) -> ReviewStatus:
    """Resolve one status for a non-stopping run from what it observed.

    Priority: any findings win over any invalid verdict, which wins over
    any agent-run failure, which wins over a clean pass.
    """
    if has_findings:
        return "findings"
    if saw_invalid_response:
        return "invalid-response"
    if saw_unavailable:
        return "unavailable"
    return "pass"


__all__ = [
    "ReviewFinding",
    "ReviewOutcome",
    "ReviewStatus",
    "combined_review_status",
]
