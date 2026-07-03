from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from konpy.config._inheritance_shared import (
    _ConfigOrigin,
    _contains_origin,
    _dedupe_plugins,
    _format_cycle,
    _format_package_lookup_error,
    _local_origin,
    _package_origin,
)
from konpy.config.errors import Err, Ok, Result
from konpy.config.package_json import PackageJsonLookupFailure, find_package_konpy_json
from konpy.config.source_resolver import classify_source


def collect_config_plugins(
    *,
    raw: Mapping[str, object],
    config_path: Path,
) -> Result[list[str]]:
    """Collect plugin distribution names declared by a config and everything it extends."""
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


def _collect_plugins_from_raw_config(
    *,
    raw: object,
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
    lookup = find_package_konpy_json(value)
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
