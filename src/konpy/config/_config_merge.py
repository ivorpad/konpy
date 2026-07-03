from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from konpy.config._inheritance_shared import _ConfigOrigin, _dedupe_plugins
from konpy.config.errors import Err, Ok, Result
from konpy.config.reference_expander import deep_merge
from konpy.config.source_resolver import classify_source


@dataclass(frozen=True)
class _ConventionEntry:
    value: object
    origin_id: str


@dataclass(frozen=True)
class _MergedRawConfig:
    data: dict[str, object]
    conventions: list[_ConventionEntry]


def _normalize_inherited_convention_sources(
    *,
    data: dict[str, object],
    origin: _ConfigOrigin,
    extends_value: str | None,
    including_origin: _ConfigOrigin | None,
) -> Result[dict[str, object]]:
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
    base_plugins: object,
    overlay_plugins: object,
) -> list[str]:
    values: list[str] = []

    if isinstance(base_plugins, list):
        values.extend(value for value in base_plugins if isinstance(value, str))
    if isinstance(overlay_plugins, list):
        values.extend(value for value in overlay_plugins if isinstance(value, str))

    return _dedupe_plugins(values)


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


def _raw_convention_name(entry: object) -> str | None:
    if isinstance(entry, Mapping):
        name = entry.get("name")
        if isinstance(name, str):
            return name

    return None
