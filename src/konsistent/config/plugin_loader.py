from __future__ import annotations

from collections.abc import Sequence
from importlib import metadata

from konsistent.config._plugin_internal import (
    PREDICATE_PLUGIN_ENTRY_POINT_GROUP,
    _build_forbidden_message_provider,
    _build_value_adapter,
    _dedupe_plugin_names,
    _load_descriptor,
    _predicate_entry_points,
    _validate_descriptor,
)
from konsistent.config.errors import Err, Ok, Result
from konsistent.config.package_json import is_valid_distribution_name
from konsistent.predicates.registry import (
    PluginOrigin,
    PredicateHandler,
    PredicateRegistry,
    builtin_predicate_registry,
    wrap_plugin_handler,
)

_DISTRIBUTION_NAME_DISPLAY_PATTERN = "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]"


def load_plugin_registry(*, plugins: Sequence[str] | None) -> Result[PredicateRegistry]:
    """Load and validate the predicate plugins named in config, merged onto the builtins."""
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
    """Alias for load_plugin_registry, kept for call sites that predate its rename."""
    return load_plugin_registry(plugins=plugins)


__all__ = [
    "PREDICATE_PLUGIN_ENTRY_POINT_GROUP",
    "load_plugin_registry",
    "load_predicate_plugins",
]
