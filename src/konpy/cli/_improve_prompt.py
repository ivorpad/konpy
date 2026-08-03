"""Prompt construction for `konpy improve`.

Split out of `konpy.cli.improve` to keep that module under the project's
per-module line limit; `improve.py` re-exports these names under its own
`__all__` so the public import path is unchanged.
"""

from __future__ import annotations

from konpy.core.report import ReportFunctionGroup
from konpy.predicates.restrict_duplicate_functions import FIX_HINT

_CONSTRAINTS = """\
Constraints:
- Work read-only. You have read-only tools; do not attempt to edit, create,
  or delete any file, and do not assume a later step will apply anything for
  you -- your only output is the diff below.
- Verify by reading the actual files before deciding. The finding above is a
  summary, not a substitute for reading each member -- confirm the bodies
  really are duplicates and look at how each one is used before proposing a
  fix.
- Respect this repository's deployment and isolation model. If two copies
  must stay independently deployable or buildable (e.g. one lives in a
  scaffold/template that gets rendered per-project, a vendored snapshot, or a
  separately packaged/isolated component), do not propose an extraction that
  would break that isolation. Aligning the copies, or pushing the fix into
  the scaffold/template they are generated from, is a valid answer when a
  shared-helper extraction would break isolation.
- The diff must apply cleanly with `patch -p0` from the repository root.

Your ENTIRE output must be exactly two things, in this order, and nothing
else -- no preamble, no restated instructions, no follow-up questions:
1. A unified diff implementing the fix.
2. A rationale of 8 lines or fewer explaining what you changed and why."""


def format_finding_block(group: ReportFunctionGroup) -> str:
    """Render one duplicate-function group as the prompt's finding block."""
    lines = [
        f'Duplicate function "{group.name}" '
        f"(x{len(group.members)} copies, {group.statement_count} statements each)"
    ]
    if group.name_variants:
        lines.append(f"Also seen under these names: {', '.join(group.name_variants)}")
    for path, line in group.members:
        lines.append(f"  - {path}:{line}")
    if group.is_cross_component:
        lines.append(
            "Members span more than one component (cross-component duplication)."
        )
    lines.append(f"fix_hint: {FIX_HINT}")
    return "\n".join(lines)


def build_improve_prompt(group: ReportFunctionGroup) -> str:
    """Build the read-only agent prompt for one duplicate-function finding."""
    return f"""\
You are konpy improve, a read-only assistant that proposes a fix for one
duplicate-function finding from `konpy report`'s duplication lane.

Finding:
{format_finding_block(group)}

{_CONSTRAINTS}
"""


__all__ = ["build_improve_prompt", "format_finding_block"]
