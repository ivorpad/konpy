from __future__ import annotations

import re
from collections.abc import Sequence
from importlib import metadata
from typing import Any

from pydantic import TypeAdapter

from konsistent.config.errors import Err, Ok, Result
from konsistent.config.package_json import is_valid_distribution_name
from konsistent.plugin import PredicatePlugin
from konsistent.predicates.registry import (
    ForbiddenMessageProvider,
    PluginOrigin,
    PredicateHandler,
    PredicateRegistry,
    builtin_predicate_registry,
    wrap_plugin_handler,
)

PREDICATE_PLUGIN_ENTRY_POINT_GROUP = "konsistent.predicates"
_DISTRIBUTION_NAME_DISPLAY_PATTERN = "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]"


def load_plugin_registry(*, plugins: Sequence[str] | None) -> Result[PredicateRegistry]:
    base_registry = builtin_predicate_registry()
    plugin_names = _dedupe_plugin_names(plugins or [])

    if not plugin_names:
        return Ok(base_registry)

    handlers: dict[str, PredicateHandler] = dict(base_registry.handlers)
    ast_predicates = set(base_registry.ast_predicates)
    item_level_must_not_predicates = set(base_registry.item_level_must_not_predicates)
    value_adapters = dict(base_registry.plugin_value_adapters)
    forbidden_messages = dict(base_registry.plugin_forbidden_messages)
    validate_placeholders = dict(base_registry.plugin_validate_placeholders)
    origins = dict(base_registry.plugin_origins)

    for plugin_name in plugin_names:
        if not isinstance(plugin_name, str):
            return Err(f'Plugin "{plugin_name}": plugin entries must be strings.')

        if not is_valid_distribution_name(plugin_name):
            return Err(
                f'Plugin "{plugin_name}": invalid Python distribution name. Plugin names '
                f"must match {_DISTRIBUTION_NAME_DISPLAY_PATTERN}."
            )

        try:
            distribution = metadata.distribution(plugin_name)
        except metadata.PackageNotFoundError:
            return Err(
                f'Plugin "{plugin_name}": installed Python distribution not found. Install '
                "it or remove it from plugins."
            )

        entry_points_result = _predicate_entry_points(
            distribution=distribution,
            requested_name=plugin_name,
        )
        if isinstance(entry_points_result, Err):
            return entry_points_result

        entry_points = entry_points_result.value
        if not entry_points:
            return Err(
                f'Plugin "{plugin_name}": no entry points found in group '
                f'"{PREDICATE_PLUGIN_ENTRY_POINT_GROUP}".'
            )

        for entry_point in entry_points:
            origin = PluginOrigin(
                distribution_name=plugin_name,
                entry_point_name=entry_point.name,
            )
            descriptor_result = _load_descriptor(
                distribution_name=plugin_name,
                entry_point=entry_point,
            )
            if isinstance(descriptor_result, Err):
                return descriptor_result

            descriptor = descriptor_result.value

            validation_result = _validate_descriptor(
                descriptor=descriptor,
                origin=origin,
                builtin_keys=base_registry.handlers.keys(),
                plugin_origins=origins,
            )
            if isinstance(validation_result, Err):
                return validation_result

            adapter_result = _build_value_adapter(descriptor=descriptor, origin=origin)
            if isinstance(adapter_result, Err):
                return adapter_result

            key = descriptor.key
            handlers[key] = wrap_plugin_handler(descriptor)
            value_adapters[key] = adapter_result.value
            forbidden_messages[key] = _build_forbidden_message_provider(descriptor)
            validate_placeholders[key] = descriptor.validate_placeholders
            origins[key] = origin

            if descriptor.uses_ast:
                ast_predicates.add(key)
            if descriptor.item_level_must_not:
                item_level_must_not_predicates.add(key)

    return Ok(
        PredicateRegistry(
            handlers=handlers,
            ast_predicates=frozenset(ast_predicates),
            item_level_must_not_predicates=frozenset(item_level_must_not_predicates),
            plugin_value_adapters=value_adapters,
            plugin_forbidden_messages=forbidden_messages,
            plugin_validate_placeholders=validate_placeholders,
            plugin_origins=origins,
        )
    )


def load_predicate_plugins(*, plugins: Sequence[str] | None) -> Result[PredicateRegistry]:
    return load_plugin_registry(plugins=plugins)


def _dedupe_plugin_names(plugin_names: Sequence[str]) -> list[str]:
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
    builtin_keys: Sequence[str] | Any,
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
) -> Result[TypeAdapter[Any]]:
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
        def callable_provider(value: Any, context: Any) -> str:
            return template(expected=value, context=context)

        return callable_provider

    def string_provider(value: Any, context: Any) -> str:
        raw_value = str(value)
        resolved_value = context.resolve_template(value) if isinstance(value, str) else raw_value
        return str(template).format(value=raw_value, resolved_value=resolved_value)

    return string_provider


__all__ = [
    "PREDICATE_PLUGIN_ENTRY_POINT_GROUP",
    "load_plugin_registry",
    "load_predicate_plugins",
]
