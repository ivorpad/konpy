from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from konsistent.config._must_block_expansion import expand_must_block_reference
from konsistent.config._reference_helpers import (
    _format_validation_error_with_prefix,
    _lookup_reusable,
    _to_alias_dict,
    _validation_context,
    deep_merge,
)
from konsistent.config.errors import Err, Ok, Result, format_validation_error
from konsistent.config.schema import ConventionV1
from konsistent.config.source_resolver import SourceMap


@dataclass(frozen=True)
class ExpandedReferences:
    """The result of expanding a raw ``conventions`` list into materialized conventions."""

    conventions: list[ConventionV1]
    identifiers: list[str]


def expand_references(
    *,
    conventions: Sequence[object],
    source_map: SourceMap,
    predicate_registry: object | None = None,
) -> Result[ExpandedReferences]:
    """Expand every entry in a raw ``conventions`` list into a materialized ``ConventionV1``."""
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
    predicate_registry: object | None = None,
) -> Result[ConventionV1]:
    """Expand a bare string reference (``"vendor/name"``) into a materialized convention."""
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

    candidate: dict[str, object] = {
        "name": reusable_data["name"],
        "description": reusable_data["description"],
        "paths": reusable_data["paths"],
    }
    for key in ("must", "mustNot", "severity", "excludeFiles", "hint"):
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
    entry: Mapping[str, object],
    index: int,
    source_map: SourceMap,
    predicate_registry: object | None = None,
) -> Result[ConventionV1]:
    """Expand a ``{ use: "vendor/name", ... }`` reference into a materialized convention."""
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

    base: dict[str, object] = {
        "name": reusable_data["name"],
        "description": reusable_data["description"],
    }
    for key in ("must", "mustNot", "severity", "paths", "excludeFiles", "hint"):
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


def _expand_hand_written(
    *,
    entry: object,
    index: int,
    source_map: SourceMap,
    predicate_registry: object | None,
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

    resolved_blocks: list[object] = []
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
