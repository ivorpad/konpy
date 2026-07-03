"""Prompt construction for `konsistent hook-propose`."""

from __future__ import annotations

from collections.abc import Sequence

from konsistent.cli._extract_rules_prompt import pack_contract_and_rubric
from konsistent.cli._propose_support import AggregatedFinding


def build_propose_prompt(
    *,
    aggregated: Sequence[AggregatedFinding],
    predicates_reference: str,
) -> str:
    """Build the agent prompt that promotes recurring hook failures into a pack."""
    finding_blocks = "\n\n".join(
        _format_finding_block(index=index, finding=finding)
        for index, finding in enumerate(aggregated, start=1)
    )

    return f"""\
You convert recurring konsistent hook agentic verification failures into a
reviewable reusable convention pack.

{pack_contract_and_rubric()}

Evidence-sufficiency rubric:
- Propose conventions only where occurrences show a recurring generalizable pattern.
- A single occurrence is weak evidence. Propose from it only if the reasons make
  the pattern unambiguous; otherwise report it in "unmapped" with reason
  "insufficient evidence".
- Base every proposal only on the evidence shown. Never generalize beyond the
  matched files, prompts, and reasons.

Never propose or reference a konsistent ignore suppression comment; suppressions
require explicit human approval and are out of scope.

{finding_blocks}

--- FULL docs/reference/predicates.md START ---
{predicates_reference}
--- FULL docs/reference/predicates.md END ---
"""


def _format_finding_block(*, index: int, finding: AggregatedFinding) -> str:
    file_lines = "\n".join(f"- {path}" for path in finding.file_paths)
    reason_lines = "\n".join(f"- {reason}" for reason in finding.reasons)

    return f"""## Finding group {index} (occurrences: {finding.occurrences}, agent: {finding.agent})

Verification prompt:
--- PROMPT START ---
{finding.prompt}
--- PROMPT END ---

Failed files:
{file_lines}

Sample reasons:
{reason_lines}"""


__all__ = ["build_propose_prompt"]
