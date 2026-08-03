"""Duplicate-function group selection for `konpy improve`.

Reuses the zero-config report's structure-collection and duplication-index
plumbing (`konpy.core.report` / `konpy.core._report_duplication`) without its
unused-code, coverage, conventions, or external-tool lanes -- `konpy improve`
only ever needs the duplicate-function groups, so it skips everything else
`assemble_report` would otherwise run.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from konpy.config.errors import Err, Ok, Result
from konpy.core._report_duplication import _duplication
from konpy.core._report_model import ReportFunctionGroup
from konpy.core.filesystem import FileSystem
from konpy.core.report import _collect_structures


def collect_duplicate_function_groups(
    file_system: FileSystem, *, root: Path
) -> tuple[ReportFunctionGroup, ...]:
    """Return duplicate-function groups in `konpy report`'s ranking order.

    Cross-component groups lead, ties break by weighted size (member count x
    statement count) then name -- the same ordering the report renders, so
    the default (no `--group`) selection always matches "the top finding".
    """
    source_cache: dict[str, str] = {}
    collected = _collect_structures(file_system, source_cache, root=root)
    _literal_groups, function_groups = _duplication(
        collected.structures,
        collected.test_paths,
        collected.generated,
        template=collected.vendor.template_files,
        vendored=collected.vendor.vendored_files,
    )
    return function_groups


def select_group(
    groups: Sequence[ReportFunctionGroup], name: str | None
) -> Result[ReportFunctionGroup]:
    """Pick the group named `name`, or the top-ranked one when `name` is None.

    `groups` must already be in the report's ranking order (see
    `collect_duplicate_function_groups`). A canonical function name is not
    guaranteed unique across fingerprints (e.g. two unrelated duplicate
    `__init__` clusters), so a `name` match can be ambiguous as well as
    missing; both cases exit the caller with an explanatory message instead
    of guessing.
    """
    if not groups:
        return Err("No duplicate-function groups found in this codebase.")

    if name is None:
        return Ok(groups[0])

    matches = [group for group in groups if group.name == name]
    if not matches:
        available = ", ".join(group.name for group in groups)
        return Err(f'Unknown group "{name}". Available groups: {available}.')

    if len(matches) > 1:
        locations = "; ".join(
            f"{match.members[0][0]}:{match.members[0][1]}" for match in matches
        )
        return Err(
            f'Ambiguous group "{name}": {len(matches)} separate duplicate '
            f"clusters share this function name ({locations}). --group does "
            "not yet disambiguate by location; omit --group to use the "
            "top-ranked cluster."
        )

    return Ok(matches[0])


__all__ = ["collect_duplicate_function_groups", "select_group"]
