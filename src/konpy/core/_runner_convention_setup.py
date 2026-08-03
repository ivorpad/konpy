"""Attaching convention-level description/hint metadata to diagnostics.

`must`/`mustNot` block normalization lives in `core.policy` (shared by the
runner and `explain`); this module keeps only the post-evaluation metadata
step, which stays close to the diagnostics it decorates.
"""

from __future__ import annotations

from dataclasses import replace

from konpy.core.diagnostics import Diagnostic


def _with_convention_metadata(
    diagnostics: list[Diagnostic],
    *,
    description: str | None,
    hint: str | None,
) -> list[Diagnostic]:
    if description is None and hint is None:
        return diagnostics

    return [
        replace(
            diagnostic,
            description=diagnostic.description or description,
            hint=diagnostic.hint or hint,
        )
        for diagnostic in diagnostics
    ]
