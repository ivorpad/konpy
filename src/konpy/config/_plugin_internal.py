"""Private helpers for loading and validating predicate-plugin descriptors.

Split out of plugin_loader.py to keep that module's public surface small;
everything here is an implementation detail of load_plugin_registry.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from importlib import metadata
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from konpy.config.errors import Err, Ok, Result
from konpy.core.context import PredicateContext
from konpy.plugin import PredicatePlugin

if TYPE_CHECKING:
    # konpy.predicates.registry imports konpy.config.schema at module
    # level, so importing it unconditionally here would cycle back through
    # this package's __init__; both names are only used in annotations.
    from konpy.predicates.registry import ForbiddenMessageProvider, PluginOrigin

PREDICATE_PLUGIN_ENTRY_POINT_GROUP = "konpy.predicates"


def _dedupe_plugin_names(plugin_names: Collection[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for plugin_name in plugin_names:
        is_str = isinstance(plugin_name, str)
        canonical = _canonical_distribution_name(plugin_name) if is_str else ""
        if canonical in seen:
            continue

        seen.add(canonical)
        result.append(plugin_name)

    return result


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _predicate_entry_points(
    *,
    distribution: metadata.Distribution,
    requested_name: str,
) -> Result[tuple[metadata.EntryPoint, ...]]:
    try:
        return Ok(
            tuple(
                entry_point
                for entry_point in distribution.entry_points
                if entry_point.group == PREDICATE_PLUGIN_ENTRY_POINT_GROUP
            )
        )
    except Exception as error:
        return Err(f'Plugin "{requested_name}": could not read entry points: {error}')


def _load_descriptor(
    *,
    distribution_name: str,
    entry_point: metadata.EntryPoint,
) -> Result[PredicatePlugin]:
    try:
        loaded = entry_point.load()
    except Exception as error:
        return Err(
            f'Plugin "{distribution_name}" entry point "{entry_point.name}": failed to '
            f"load: {error}"
        )

    if isinstance(loaded, PredicatePlugin):
        return Ok(loaded)

    if callable(loaded):
        try:
            returned = loaded()
        except Exception as error:
            return Err(
                f'Plugin "{distribution_name}" entry point "{entry_point.name}": callable '
                f"descriptor failed: {error}"
            )

        if isinstance(returned, PredicatePlugin):
            return Ok(returned)

    return Err(
        f'Plugin "{distribution_name}" entry point "{entry_point.name}" must load a '
        "PredicatePlugin instance or a zero-argument callable returning PredicatePlugin."
    )


def _validate_descriptor(
    *,
    descriptor: PredicatePlugin,
    origin: PluginOrigin,
    builtin_keys: Collection[str],
    plugin_origins: dict[str, PluginOrigin],
) -> Result[None]:
    if not isinstance(descriptor.key, str) or descriptor.key == "":
        return _invalid_descriptor(origin=origin, detail="key must be a non-empty string")

    if not callable(descriptor.handler):
        return _invalid_descriptor(origin=origin, detail="handler must be callable")

    if not isinstance(descriptor.forbidden_message_template, str) and not callable(
        descriptor.forbidden_message_template
    ):
        return _invalid_descriptor(
            origin=origin,
            detail="forbidden_message_template must be a string or callable",
        )

    if not isinstance(descriptor.uses_ast, bool):
        return _invalid_descriptor(origin=origin, detail="uses_ast must be a boolean")

    if not isinstance(descriptor.item_level_must_not, bool):
        return _invalid_descriptor(
            origin=origin,
            detail="item_level_must_not must be a boolean",
        )

    if not isinstance(descriptor.validate_placeholders, bool):
        return _invalid_descriptor(
            origin=origin,
            detail="validate_placeholders must be a boolean",
        )

    if descriptor.key in builtin_keys:
        return Err(
            f'Plugin "{origin.distribution_name}" entry point "{origin.entry_point_name}" '
            f'declares predicate key "{descriptor.key}", which conflicts with a built-in '
            "predicate. Choose a unique plugin predicate key."
        )

    existing_origin = plugin_origins.get(descriptor.key)
    if existing_origin is not None:
        return Err(
            f'Plugin "{origin.distribution_name}" entry point "{origin.entry_point_name}" '
            f'declares predicate key "{descriptor.key}", which conflicts with plugin '
            f'"{existing_origin.distribution_name}" entry point '
            f'"{existing_origin.entry_point_name}". Plugin predicate keys must be unique.'
        )

    return Ok(None)


def _invalid_descriptor(*, origin: PluginOrigin, detail: str) -> Err:
    return Err(
        f'Plugin "{origin.distribution_name}" entry point "{origin.entry_point_name}" '
        f"declares an invalid predicate descriptor: {detail}."
    )


def _build_value_adapter(
    *,
    descriptor: PredicatePlugin,
    origin: PluginOrigin,
) -> Result[TypeAdapter[object]]:
    if isinstance(descriptor.value_model, TypeAdapter):
        return Ok(descriptor.value_model)

    try:
        return Ok(TypeAdapter(descriptor.value_model))
    except Exception as error:
        return _invalid_descriptor(
            origin=origin,
            detail=f"value_model could not be adapted by pydantic: {error}",
        )


def _build_forbidden_message_provider(
    descriptor: PredicatePlugin,
) -> ForbiddenMessageProvider:
    template = descriptor.forbidden_message_template

    if callable(template) and not isinstance(template, str):
        def callable_provider(value: object, context: PredicateContext) -> str:
            return template(expected=value, context=context)

        return callable_provider

    def string_provider(value: object, context: PredicateContext) -> str:
        raw_value = str(value)
        resolved_value = context.resolve_template(value) if isinstance(value, str) else raw_value
        return str(template).format(value=raw_value, resolved_value=resolved_value)

    return string_provider


__all__: list[str] = []
