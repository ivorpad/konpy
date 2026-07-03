from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from konsistent.config._config_merge import (
    _apply_disable,
    _ConventionEntry,
    _merge_layers,
    _MergedRawConfig,
    _normalize_inherited_convention_sources,
)
from konsistent.config._inheritance_shared import (
    _ConfigOrigin,
    _contains_origin,
    _format_cycle,
    _format_package_lookup_error,
    _local_origin,
    _package_origin,
)
from konsistent.config.errors import Err, Ok, Result, format_validation_error
from konsistent.config.package_json import PackageJsonLookupFailure, find_package_konsistent_json
from konsistent.config.schema import RawConfigV1
from konsistent.config.source_resolver import classify_source


def resolve_config_inheritance(
    *,
    raw: Mapping[str, object],
    config_path: Path,
    predicate_registry: object | None = None,
) -> Result[dict[str, object]]:
    """Resolve a config's ``extends`` chain into a single merged raw config document."""
    root_path = config_path.resolve()
    root_origin = _local_origin(root_path)
    resolved = _resolve_raw_config(
        raw=raw,
        origin=root_origin,
        stack=(),
        is_root=True,
        extends_value=None,
        including_origin=None,
        predicate_registry=predicate_registry,
    )
    if isinstance(resolved, Err):
        return resolved

    merged = resolved.value
    data = dict(merged.data)
    data.pop("extends", None)
    data.pop("disable", None)
    data["conventions"] = [entry.value for entry in merged.conventions]
    return Ok(data)


def _resolve_raw_config(
    *,
    raw: object,
    origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    is_root: bool,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
    predicate_registry: object | None,
) -> Result[_MergedRawConfig]:
    parsed_result = _validate_raw_config(
        raw=raw,
        origin=origin,
        is_root=is_root,
        extends_value=extends_value,
        including_origin=including_origin,
        predicate_registry=predicate_registry,
    )
    if isinstance(parsed_result, Err):
        return parsed_result

    data = parsed_result.value.model_dump(by_alias=True, exclude_none=True)
    extends = list(data.pop("extends", []) or [])
    disable = list(data.pop("disable", []) or [])
    current_conventions = list(data.pop("conventions", []))

    if not is_root:
        normalized_result = _normalize_inherited_convention_sources(
            data=data,
            origin=origin,
            extends_value=extends_value,
            including_origin=including_origin,
        )
        if isinstance(normalized_result, Err):
            return normalized_result
        data = normalized_result.value

    current_stack = (*stack, origin)
    merged_parents = _MergedRawConfig(data={}, conventions=[])

    for value in extends:
        parent_result = _load_extended_config(
            value=value,
            including_origin=origin,
            stack=current_stack,
            predicate_registry=predicate_registry,
        )
        if isinstance(parent_result, Err):
            return parent_result

        merged_parents = _merge_layers(base=merged_parents, overlay=parent_result.value)

    current_layer = _MergedRawConfig(
        data=data,
        conventions=[
            _ConventionEntry(value=value, origin_id=origin.id) for value in current_conventions
        ],
    )
    merged = _merge_layers(base=merged_parents, overlay=current_layer)

    if disable:
        merged = _MergedRawConfig(
            data=merged.data,
            conventions=_apply_disable(
                conventions=merged.conventions,
                disabled_names=set(disable),
                current_origin_id=origin.id,
            ),
        )

    return Ok(merged)


def _validate_raw_config(
    *,
    raw: object,
    origin: _ConfigOrigin,
    is_root: bool,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
    predicate_registry: object | None,
) -> Result[RawConfigV1]:
    try:
        return Ok(
            RawConfigV1.model_validate(
                raw,
                context=_validation_context(predicate_registry),
            )
        )
    except ValidationError as error:
        issues = format_validation_error(error)
        if is_root:
            return Err(f"Invalid config:\n{issues}")

        including_label = including_origin.label if including_origin is not None else "<unknown>"
        return Err(
            f'Config extends "{extends_value}" from {including_label}: invalid config at '
            f"{origin.label}:\n{issues}"
        )


def _load_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    predicate_registry: object | None,
) -> Result[_MergedRawConfig]:
    kind = classify_source(value)

    if kind == "empty":
        return Err(f"Config extends entry in {including_origin.label} has empty value.")

    if kind == "package":
        return _load_package_extended_config(
            value=value,
            including_origin=including_origin,
            stack=stack,
            predicate_registry=predicate_registry,
        )

    return _load_path_extended_config(
        value=value,
        including_origin=including_origin,
        stack=stack,
        predicate_registry=predicate_registry,
    )


def _load_path_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    predicate_registry: object | None,
) -> Result[_MergedRawConfig]:
    value_path = Path(value)

    if including_origin.local_dir is None and not value_path.is_absolute():
        return Err(
            f'Config extends "{value}" from {including_origin.label}: relative local-path '
            "extends are not supported inside package-loaded configs. Use an absolute path "
            "or an installed package name."
        )

    base_dir = including_origin.local_dir or Path()
    resolved_path = (base_dir / value_path).resolve()
    origin = _local_origin(resolved_path)

    if _contains_origin(stack=stack, origin=origin):
        return Err(f"Config inheritance cycle detected: {_format_cycle(stack, origin)}.")

    try:
        raw_text = resolved_path.read_text(encoding="utf-8")
    except OSError:
        return Err(
            f'Config extends "{value}" from {including_origin.label}: could not read file at '
            f"{resolved_path}."
        )

    try:
        json_value = json.loads(raw_text)
    except json.JSONDecodeError:
        return Err(
            f'Config extends "{value}" from {including_origin.label}: malformed JSON at '
            f"{resolved_path}."
        )

    return _resolve_raw_config(
        raw=json_value,
        origin=origin,
        stack=stack,
        is_root=False,
        extends_value=value,
        including_origin=including_origin,
        predicate_registry=predicate_registry,
    )


def _load_package_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    predicate_registry: object | None,
) -> Result[_MergedRawConfig]:
    lookup = find_package_konsistent_json(value)
    if isinstance(lookup, PackageJsonLookupFailure):
        return Err(
            _format_package_lookup_error(
                value=value,
                including_label=including_origin.label,
                failure=lookup,
            )
        )

    origin = _package_origin(lookup)

    if _contains_origin(stack=stack, origin=origin):
        return Err(f"Config inheritance cycle detected: {_format_cycle(stack, origin)}.")

    try:
        json_value = json.loads(lookup.raw)
    except json.JSONDecodeError:
        return Err(
            f'Config extends "{value}" from {including_origin.label}: malformed JSON at '
            f"{lookup.location_label}."
        )

    return _resolve_raw_config(
        raw=json_value,
        origin=origin,
        stack=stack,
        is_root=False,
        extends_value=value,
        including_origin=including_origin,
        predicate_registry=predicate_registry,
    )


def _validation_context(predicate_registry: object | None) -> dict[str, object] | None:
    if predicate_registry is None:
        return None
    return predicate_registry.validation_context()
