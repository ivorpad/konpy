from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import TypeAdapter

from konpy.config.schema import MustPredicatesV1
from konpy.predicates._handlers import (
    AST_PREDICATES,
    CROSS_FILE_PREDICATES,
    ITEM_LEVEL_MUST_NOT_PREDICATES,
    PREDICATE_HANDLERS,
    PredicateHandler,
)
from konpy.predicates._plugin import (
    ForbiddenMessageProvider,
    PluginOrigin,
    wrap_plugin_handler,
)

__all__ = [
    "AST_PREDICATES",
    "CROSS_FILE_PREDICATES",
    "ITEM_LEVEL_MUST_NOT_PREDICATES",
    "PREDICATE_HANDLERS",
    "ForbiddenMessageProvider",
    "PluginOrigin",
    "PredicateHandler",
    "PredicateRegistry",
    "builtin_predicate_registry",
    "iter_predicate_items",
    "validation_context",
    "wrap_plugin_handler",
]


@dataclass(frozen=True, kw_only=True)
class PredicateRegistry:
    """The full set of predicate handlers and plugin metadata for a run."""

    handlers: Mapping[str, PredicateHandler]
    ast_predicates: frozenset[str]
    item_level_must_not_predicates: frozenset[str]
    plugin_value_adapters: Mapping[str, TypeAdapter[object]]
    plugin_forbidden_messages: Mapping[str, ForbiddenMessageProvider]
    plugin_validate_placeholders: Mapping[str, bool]
    plugin_origins: Mapping[str, PluginOrigin]
    cross_file_predicates: frozenset[str] = frozenset()

    def validation_context(self) -> dict[str, PredicateRegistry]:
        """Build the pydantic validation context that carries this registry."""
        return {"predicate_registry": self}


def builtin_predicate_registry() -> PredicateRegistry:
    """Build the PredicateRegistry containing only the built-in predicate handlers."""
    return PredicateRegistry(
        handlers=dict(PREDICATE_HANDLERS),
        ast_predicates=frozenset(AST_PREDICATES),
        item_level_must_not_predicates=frozenset(ITEM_LEVEL_MUST_NOT_PREDICATES),
        plugin_value_adapters={},
        plugin_forbidden_messages={},
        plugin_validate_placeholders={},
        plugin_origins={},
        cross_file_predicates=frozenset(CROSS_FILE_PREDICATES),
    )


def validation_context(registry: PredicateRegistry) -> dict[str, PredicateRegistry]:
    """Build the pydantic validation context that carries the given registry."""
    return registry.validation_context()


def iter_predicate_items(must: MustPredicatesV1) -> list[tuple[str, object]]:
    """Yield (predicate name, value) pairs for every predicate set on a must block."""
    items: list[tuple[str, object]] = []
    for field_name, field in type(must).model_fields.items():
        value = getattr(must, field_name)
        if value is not None:
            items.append((field.alias or field_name, value))

    for key, value in (must.model_extra or {}).items():
        items.append((key, value))

    return items
