from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel, ValidationError

from konpy.config.errors import Err, Ok, Result, format_error_path
from konpy.config.schema import CONVENTION_REF_PATTERN, ReusableConventionV1
from konpy.config.source_resolver import SourceMap

_STRING_REF_REGEX = re.compile(f"^{CONVENTION_REF_PATTERN}$")


def deep_merge(
    *,
    base: Mapping[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    """Recursively merge ``override`` on top of ``base``, merging nested mappings."""
    result = dict(base)

    for key, override_value in override.items():
        base_value = result.get(key)

        if _is_plain_mapping(base_value) and _is_plain_mapping(override_value):
            result[key] = deep_merge(base=base_value, override=override_value)
            continue

        result[key] = override_value

    return result


def _lookup_reusable(
    *,
    ref: str,
    index: int,
    source_map: SourceMap,
) -> Result[tuple[ReusableConventionV1, str, str]]:
    if _STRING_REF_REGEX.fullmatch(ref) is None:
        return Err(
            f'Invalid convention reference "{ref}" in conventions[{index}]. Expected '
            'format "<vendor>/<name>".'
        )

    prefix, name = ref.split("/", 1)
    convention_map = source_map.get(prefix)
    if convention_map is None:
        return Err(
            f'Unknown convention source "{prefix}" referenced in conventions[{index}]. '
            "Declare it in conventionSources or fix the typo."
        )

    reusable = convention_map.get(name)
    if reusable is None:
        available = ", ".join(convention_map)
        return Err(
            f'No convention "{name}" in source "{prefix}". The package exports: '
            f"{available}."
        )

    return Ok((reusable, prefix, name))


def _format_validation_error_with_prefix(error: ValidationError, prefix: str) -> str:
    lines: list[str] = []
    for issue in error.errors():
        path = format_error_path(issue.get("loc", ()))
        suffix = f".{path}" if path else ""
        lines.append(f"  - {prefix}{suffix}: {issue['msg']}")
    return "\n".join(lines)


def _to_alias_dict(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping-like config entry, got {type(value).__name__}")


def _is_plain_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and not isinstance(value, BaseModel)


def _validation_context(predicate_registry: object | None) -> dict[str, object] | None:
    if predicate_registry is None:
        return None
    return predicate_registry.validation_context()
