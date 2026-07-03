from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from konpy.config._reference_helpers import (
    _format_validation_error_with_prefix,
    _lookup_reusable,
    _to_alias_dict,
    _validation_context,
    deep_merge,
)
from konpy.config.errors import Err, Ok, Result
from konpy.config.schema import MustBlockV1
from konpy.config.source_resolver import SourceMap


def expand_must_block_reference(
    *,
    ref: str,
    overrides: Mapping[str, object],
    convention_index: int,
    block_index: int,
    source_map: SourceMap,
    predicate_registry: object | None = None,
) -> Result[MustBlockV1]:
    """Expand a string or ``use``-form reference inside a convention's ``must``/``mustNot`` list."""
    location = f"conventions[{convention_index}].must[{block_index}]"

    lookup = _lookup_reusable(ref=ref, index=convention_index, source_map=source_map)
    if isinstance(lookup, Err):
        return Err(lookup.error.replace(f"conventions[{convention_index}]", location))

    reusable, prefix, name = lookup.value
    reusable_data = _to_alias_dict(reusable)

    top_level_only: list[str] = []
    if "paths" in reusable_data:
        top_level_only.append("paths")
    if "severity" in reusable_data:
        top_level_only.append("severity")

    if top_level_only:
        fields = ", ".join(f'"{field}"' for field in top_level_only)
        return Err(
            f'Convention "{prefix}/{name}" referenced in {location} declares '
            f"top-level-only field(s) {fields}. Such conventions can only be referenced "
            "at the top level of conventions[]. Either remove the field(s) from the "
            "source convention, or move the reference out of must[]."
        )

    base: dict[str, object] = {}
    for key in ("must", "mustNot", "name", "description", "hint", "if", "for", "excludeFiles"):
        if key in reusable_data:
            base[key] = reusable_data[key]

    merged = deep_merge(base=base, override=overrides)

    try:
        block = MustBlockV1.model_validate(
            merged,
            context=_validation_context(predicate_registry),
        )
    except ValidationError as error:
        issues = _format_validation_error_with_prefix(error, location)
        return Err(
            f'Expanded must-block reference "{prefix}/{name}" failed validation at '
            f"{location}:\n{issues}"
        )

    return Ok(block)
