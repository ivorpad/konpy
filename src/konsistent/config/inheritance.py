from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from konsistent.config.errors import Err, Ok, Result, format_validation_error
from konsistent.config.package_json import (
    PackageJsonDocument,
    PackageJsonLookupFailure,
    find_package_konsistent_json,
)
from konsistent.config.reference_expander import deep_merge
from konsistent.config.schema import RawConfigV1
from konsistent.config.source_resolver import classify_source


@dataclass(frozen=True)
class _ConfigOrigin:
    id: str
    label: str
    local_dir: Path | None


@dataclass(frozen=True)
class _ConventionEntry:
    value: Any
    origin_id: str


@dataclass(frozen=True)
class _MergedRawConfig:
    data: dict[str, Any]
    conventions: list[_ConventionEntry]


def collect_config_plugins(
    *,
    raw: Mapping[str, Any],
    config_path: Path,
) -> Result[list[str]]:
    root_path = config_path.resolve()
    root_origin = _local_origin(root_path)
    collected = _collect_plugins_from_raw_config(
        raw=raw,
        origin=root_origin,
        stack=(),
        is_root=True,
        extends_value=None,
        including_origin=None,
    )
    if isinstance(collected, Err):
        return collected

    return Ok(_dedupe_plugins(collected.value))


def resolve_config_inheritance(
    *,
    raw: Mapping[str, Any],
    config_path: Path,
    predicate_registry: Any | None = None,
) -> Result[dict[str, Any]]:
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


def _collect_plugins_from_raw_config(
    *,
    raw: Any,
    origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    is_root: bool,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
) -> Result[list[str]]:
    if not isinstance(raw, Mapping):
        return Ok([])

    collected: list[str] = []
    extends = raw.get("extends")
    current_stack = (*stack, origin)

    if isinstance(extends, list):
        for value in extends:
            if not isinstance(value, str):
                continue

            parent_result = _collect_plugins_from_extended_config(
                value=value,
                including_origin=origin,
                stack=current_stack,
            )
            if isinstance(parent_result, Err):
                return parent_result
            collected.extend(parent_result.value)

    plugins = raw.get("plugins")
    if isinstance(plugins, list):
        collected.extend(value for value in plugins if isinstance(value, str))

    return Ok(collected)


def _collect_plugins_from_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
) -> Result[list[str]]:
    kind = classify_source(value)

    if kind == "empty":
        return Err(f"Config extends entry in {including_origin.label} has empty value.")

    if kind == "package":
        return _collect_plugins_from_package_extended_config(
            value=value,
            including_origin=including_origin,
            stack=stack,
        )

    return _collect_plugins_from_path_extended_config(
        value=value,
        including_origin=including_origin,
        stack=stack,
    )


def _collect_plugins_from_path_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
) -> Result[list[str]]:
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

    return _collect_plugins_from_raw_config(
        raw=json_value,
        origin=origin,
        stack=stack,
        is_root=False,
        extends_value=value,
        including_origin=including_origin,
    )


def _collect_plugins_from_package_extended_config(
    *,
    value: str,
    including_origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
) -> Result[list[str]]:
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

    return _collect_plugins_from_raw_config(
        raw=json_value,
        origin=origin,
        stack=stack,
        is_root=False,
        extends_value=value,
        including_origin=including_origin,
    )


def _resolve_raw_config(
    *,
    raw: Any,
    origin: _ConfigOrigin,
    stack: tuple[_ConfigOrigin, ...],
    is_root: bool,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
    predicate_registry: Any | None,
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
    raw: Any,
    origin: _ConfigOrigin,
    is_root: bool,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
    predicate_registry: Any | None,
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
    predicate_registry: Any | None,
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
    predicate_registry: Any | None,
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
    predicate_registry: Any | None,
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


def _format_package_lookup_error(
    *,
    value: str,
    including_label: str,
    failure: PackageJsonLookupFailure,
) -> str:
    source = f'Config extends "{value}" from {including_label}: '

    if failure.kind == "invalid-name":
        return (
            f"{source}invalid Python distribution name. Bare package sources must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
        )

    if failure.kind == "not-installed":
        return (
            f"{source}installed Python distribution not found. Install it or use a local "
            "path in extends."
        )

    if failure.kind == "missing-json":
        return (
            f"{source}installed Python distribution does not contain konsistent.json. "
            f"Looked for {_format_top_level_lookup(failure.top_level_packages)} and a "
            "distribution file named konsistent.json."
        )

    detail = f" {failure.detail}" if failure.detail else ""
    return f"{source}could not read installed Python distribution data:{detail}."


def _format_top_level_lookup(top_level_packages: tuple[str, ...]) -> str:
    if len(top_level_packages) == 1:
        return f"{top_level_packages[0]}/konsistent.json"
    if top_level_packages:
        return "one of " + ", ".join(
            f"{package_name}/konsistent.json" for package_name in top_level_packages
        )
    return "<top-level import package>/konsistent.json"


def _contains_origin(*, stack: tuple[_ConfigOrigin, ...], origin: _ConfigOrigin) -> bool:
    return any(entry.id == origin.id for entry in stack)


def _format_cycle(stack: tuple[_ConfigOrigin, ...], repeated_origin: _ConfigOrigin) -> str:
    start_index = next(
        index for index, origin in enumerate(stack) if origin.id == repeated_origin.id
    )
    cycle = (*stack[start_index:], repeated_origin)
    return " -> ".join(origin.label for origin in cycle)


def _normalize_inherited_convention_sources(
    *,
    data: dict[str, Any],
    origin: _ConfigOrigin,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
) -> Result[dict[str, Any]]:
    sources = data.get("conventionSources")
    if not isinstance(sources, Mapping):
        return Ok(data)

    normalized_sources: dict[str, str] = {}
    for prefix, value in sources.items():
        if classify_source(value) == "path":
            value_path = Path(value)
            if origin.local_dir is None:
                if not value_path.is_absolute():
                    including_label = (
                        including_origin.label if including_origin is not None else "<unknown>"
                    )
                    return Err(
                        f'Config extends "{extends_value}" from {including_label}: package '
                        f'config at {origin.label} declares relative conventionSources'
                        f'["{prefix}"] = "{value}". Relative conventionSources are not '
                        "supported inside package-loaded configs; use an absolute path or "
                        "an installed package name."
                    )

                normalized_sources[str(prefix)] = str(value_path.resolve())
                continue

            normalized_sources[str(prefix)] = str((origin.local_dir / value_path).resolve())
            continue

        normalized_sources[str(prefix)] = value

    normalized = dict(data)
    normalized["conventionSources"] = normalized_sources
    return Ok(normalized)


def _merge_layers(
    *,
    base: _MergedRawConfig,
    overlay: _MergedRawConfig,
) -> _MergedRawConfig:
    base_data = dict(base.data)
    overlay_data = dict(overlay.data)
    base_plugins = base_data.pop("plugins", None)
    overlay_plugins = overlay_data.pop("plugins", None)

    merged_data = deep_merge(base=base_data, override=overlay_data)
    merged_plugins = _merge_plugins(base_plugins=base_plugins, overlay_plugins=overlay_plugins)
    if merged_plugins:
        merged_data["plugins"] = merged_plugins

    return _MergedRawConfig(
        data=merged_data,
        conventions=_merge_conventions(
            base=base.conventions,
            overlay=overlay.conventions,
        ),
    )


def _merge_plugins(
    *,
    base_plugins: Any,
    overlay_plugins: Any,
) -> list[str]:
    values: list[str] = []

    if isinstance(base_plugins, list):
        values.extend(value for value in base_plugins if isinstance(value, str))
    if isinstance(overlay_plugins, list):
        values.extend(value for value in overlay_plugins if isinstance(value, str))

    return _dedupe_plugins(values)


def _dedupe_plugins(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        canonical = _canonical_distribution_name(value)
        if canonical in seen:
            continue

        seen.add(canonical)
        result.append(value)

    return result


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _merge_conventions(
    *,
    base: list[_ConventionEntry],
    overlay: list[_ConventionEntry],
) -> list[_ConventionEntry]:
    if not base:
        return list(overlay)

    result = list(base)
    name_to_index: dict[str, int] = {}

    for index, entry in enumerate(result):
        name = _raw_convention_name(entry.value)
        if name is not None and name not in name_to_index:
            name_to_index[name] = index

    for entry in overlay:
        name = _raw_convention_name(entry.value)
        if name is not None and name in name_to_index:
            result[name_to_index[name]] = entry
            continue

        result.append(entry)

    return result


def _apply_disable(
    *,
    conventions: list[_ConventionEntry],
    disabled_names: set[str],
    current_origin_id: str,
) -> list[_ConventionEntry]:
    if not disabled_names:
        return list(conventions)

    filtered: list[_ConventionEntry] = []
    for entry in conventions:
        name = _raw_convention_name(entry.value)
        if entry.origin_id != current_origin_id and name in disabled_names:
            continue

        filtered.append(entry)

    return filtered


def _raw_convention_name(entry: Any) -> str | None:
    if isinstance(entry, Mapping):
        name = entry.get("name")
        if isinstance(name, str):
            return name

    return None


def _local_origin(path: Path) -> _ConfigOrigin:
    return _ConfigOrigin(
        id=f"path:{path}",
        label=str(path),
        local_dir=path.parent,
    )


def _package_origin(document: PackageJsonDocument) -> _ConfigOrigin:
    return _ConfigOrigin(
        id=document.origin_id,
        label=document.location_label,
        local_dir=None,
    )


def _validation_context(predicate_registry: Any | None) -> dict[str, Any] | None:
    if predicate_registry is None:
        return None
    return predicate_registry.validation_context()


__all__ = ["collect_config_plugins", "resolve_config_inheritance"]
