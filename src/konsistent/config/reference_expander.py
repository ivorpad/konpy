from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from konsistent.config.errors import Err, Ok, Result, format_error_path, format_validation_error
from konsistent.config.schema import (
    CONVENTION_REF_PATTERN,
    ConventionV1,
    MustBlockV1,
    ReusableConventionV1,
)
from konsistent.config.source_resolver import SourceMap

_STRING_REF_REGEX = re.compile(f"^{CONVENTION_REF_PATTERN}$")


@dataclass(frozen=True)
class ExpandedReferences:
    conventions: list[ConventionV1]
    identifiers: list[str]


def expand_references(
    *,
    conventions: Sequence[Any],
    source_map: SourceMap,
    predicate_registry: Any | None = None,
) -> Result[ExpandedReferences]:
    expanded: list[ConventionV1] = []
    identifiers: list[str] = []

    for index, entry in enumerate(conventions):
        if isinstance(entry, str):
            result = expand_string_reference(
                ref=entry,
                index=index,
                source_map=source_map,
                predicate_registry=predicate_registry,
            )
            if isinstance(result, Err):
                return result
            expanded.append(result.value)
            identifiers.append(entry)
            continue

        entry_data = _to_alias_dict(entry)
        if "use" in entry_data:
            result = expand_use_reference(
                entry=entry_data,
                index=index,
                source_map=source_map,
                predicate_registry=predicate_registry,
            )
            if isinstance(result, Err):
                return result
            expanded.append(result.value)
            identifiers.append(str(entry_data["use"]))
            continue

        result = _expand_hand_written(
            entry=entry,
            index=index,
            source_map=source_map,
            predicate_registry=predicate_registry,
        )
        if isinstance(result, Err):
            return result
        convention = result.value
        expanded.append(convention)
        identifiers.append(convention.name or f"conventions[{index}]")

    return Ok(ExpandedReferences(conventions=expanded, identifiers=identifiers))


def expand_string_reference(
    *,
    ref: str,
    index: int,
    source_map: SourceMap,
    predicate_registry: Any | None = None,
) -> Result[ConventionV1]:
    lookup = _lookup_reusable(ref=ref, index=index, source_map=source_map)
    if isinstance(lookup, Err):
        return lookup

    reusable, prefix, name = lookup.value
    reusable_data = _to_alias_dict(reusable)

    if "paths" not in reusable_data:
        return Err(
            f'Convention "{prefix}/{name}" cannot be referenced by string; it has no '
            f'"paths". Use {{ use: "{prefix}/{name}", paths: [...] }} form.'
        )

    candidate: dict[str, Any] = {
        "name": reusable_data["name"],
        "description": reusable_data["description"],
        "paths": reusable_data["paths"],
    }
    for key in ("must", "mustNot", "severity", "excludeFiles"):
        if key in reusable_data:
            candidate[key] = reusable_data[key]

    try:
        convention = ConventionV1.model_validate(
            candidate,
            context=_validation_context(predicate_registry),
        )
    except ValidationError as error:
        issues = format_validation_error(error)
        return Err(
            f'Expanded convention "{prefix}/{name}" failed validation at '
            f"conventions[{index}]:\n{issues}"
        )

    return Ok(convention)


def expand_use_reference(
    *,
    entry: Mapping[str, Any],
    index: int,
    source_map: SourceMap,
    predicate_registry: Any | None = None,
) -> Result[ConventionV1]:
    ref = str(entry["use"])

    lookup = _lookup_reusable(ref=ref, index=index, source_map=source_map)
    if isinstance(lookup, Err):
        return lookup

    reusable, prefix, name = lookup.value
    reusable_data = _to_alias_dict(reusable)
    overrides = {key: value for key, value in entry.items() if key != "use"}

    if "paths" not in reusable_data and "paths" not in overrides:
        return Err(
            f'Convention "{prefix}/{name}" referenced in conventions[{index}] has no '
            '"paths". Either the reusable convention must declare paths, or the override '
            "must supply paths."
        )

    base: dict[str, Any] = {
        "name": reusable_data["name"],
        "description": reusable_data["description"],
    }
    for key in ("must", "mustNot", "severity", "paths", "excludeFiles"):
        if key in reusable_data:
            base[key] = reusable_data[key]

    merged = deep_merge(base=base, override=overrides)

    try:
        convention = ConventionV1.model_validate(
            merged,
            context=_validation_context(predicate_registry),
        )
    except ValidationError as error:
        issues = _format_validation_error_with_prefix(error, f"conventions.{index}")
        return Err(
            f'Expanded convention "{prefix}/{name}" failed validation at '
            f"conventions[{index}]:\n{issues}"
        )

    return Ok(convention)


def expand_must_block_reference(
    *,
    ref: str,
    overrides: Mapping[str, Any],
    convention_index: int,
    block_index: int,
    source_map: SourceMap,
    predicate_registry: Any | None = None,
) -> Result[MustBlockV1]:
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

    base: dict[str, Any] = {}
    for key in ("must", "mustNot", "name", "description", "if", "for", "excludeFiles"):
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


def deep_merge(
    *,
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(base)

    for key, override_value in override.items():
        base_value = result.get(key)

        if _is_plain_mapping(base_value) and _is_plain_mapping(override_value):
            result[key] = deep_merge(base=base_value, override=override_value)
            continue

        result[key] = override_value

    return result


def _expand_hand_written(
    *,
    entry: Any,
    index: int,
    source_map: SourceMap,
    predicate_registry: Any | None,
) -> Result[ConventionV1]:
    must = getattr(entry, "must", None)
    if must is None and isinstance(entry, Mapping):
        must = entry.get("must")

    if not isinstance(must, list):
        if isinstance(entry, ConventionV1):
            return Ok(entry)
        try:
            return Ok(
                ConventionV1.model_validate(
                    _to_alias_dict(entry),
                    context=_validation_context(predicate_registry),
                )
            )
        except ValidationError as error:
            issues = _format_validation_error_with_prefix(error, f"conventions.{index}")
            return Err(f"Invalid convention at conventions[{index}]:\n{issues}")

    resolved_blocks: list[Any] = []
    for block_index, block in enumerate(must):
        if isinstance(block, str):
            result = expand_must_block_reference(
                ref=block,
                overrides={},
                convention_index=index,
                block_index=block_index,
                source_map=source_map,
                predicate_registry=predicate_registry,
            )
            if isinstance(result, Err):
                return result
            resolved_blocks.append(_to_alias_dict(result.value))
            continue

        block_data = _to_alias_dict(block)
        if "use" in block_data:
            use = str(block_data["use"])
            overrides = {key: value for key, value in block_data.items() if key != "use"}
            result = expand_must_block_reference(
                ref=use,
                overrides=overrides,
                convention_index=index,
                block_index=block_index,
                source_map=source_map,
                predicate_registry=predicate_registry,
            )
            if isinstance(result, Err):
                return result
            resolved_blocks.append(_to_alias_dict(result.value))
            continue

        resolved_blocks.append(block_data)

    candidate = _to_alias_dict(entry)
    candidate["must"] = resolved_blocks

    try:
        return Ok(
            ConventionV1.model_validate(
                candidate,
                context=_validation_context(predicate_registry),
            )
        )
    except ValidationError as error:
        issues = _format_validation_error_with_prefix(error, f"conventions.{index}")
        return Err(f"Invalid convention at conventions[{index}]:\n{issues}")


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


def _to_alias_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping-like config entry, got {type(value).__name__}")


def _is_plain_mapping(value: Any) -> bool:
    return isinstance(value, Mapping) and not isinstance(value, BaseModel)


def _validation_context(predicate_registry: Any | None) -> dict[str, Any] | None:
    if predicate_registry is None:
        return None
    return predicate_registry.validation_context()


__all__ = [
    "ExpandedReferences",
    "deep_merge",
    "expand_must_block_reference",
    "expand_references",
    "expand_string_reference",
    "expand_use_reference",
]
