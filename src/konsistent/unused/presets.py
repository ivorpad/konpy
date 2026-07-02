"""Framework presets for unused-code classification.

These ship so a bare ``"unusedCode": {}`` is already low-noise. User config
values *extend* (union with) the presets, except ``allow`` which is standalone.

- ``REGISTRY_DECORATOR_PRESETS``: fnmatch-style patterns matched against a
  decorator's dotted name (call parens stripped). ``app.*`` matches ``app.get``.
- ``HOOK_NAME_PRESETS``: framework lifecycle method/attribute names. Dunders
  (``__x__``) are handled by a rule in the classifier, not listed here.
- ``MODEL_BASE_PRESETS``: base-class names whose attributes are model fields
  read dynamically (validation/serialization), so never "unused".
- ``DATACLASS_DECORATOR_PRESETS``: class decorators that also make attributes
  model fields for the purposes of this rule.
"""

from __future__ import annotations

REGISTRY_DECORATOR_PRESETS: tuple[str, ...] = (
    # pydantic
    "field_validator",
    "model_validator",
    "computed_field",
    "field_serializer",
    "model_serializer",
    "validator",
    "root_validator",
    # pytest
    "pytest.fixture",
    "fixture",
    "pytest.mark.*",
    # fastapi / flask / django rest / aws powertools resolvers
    "app.*",
    "router.*",
    "blueprint.*",
    "api.*",
    # celery
    "task",
    "shared_task",
    "celery.task",
    # click / typer
    "command",
    "group",
    "callback",
    "app.command",
    "app.callback",
    # functools / typing dispatch + overloads
    "overload",
    "typing.overload",
    "singledispatch",
    "functools.singledispatch",
    "singledispatchmethod",
    "register",
    "*.register",
)

HOOK_NAME_PRESETS: frozenset[str] = frozenset(
    {
        # pydantic lifecycle hooks / config
        "model_post_init",
        "model_config",
        "Config",
        "model_fields_set",
        "model_fields",
        # unittest / pytest lifecycle
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
        "setUpModule",
        "tearDownModule",
        "setup_method",
        "teardown_method",
        "setup_class",
        "teardown_class",
        "setup_module",
        "teardown_module",
        "setup_function",
        "teardown_function",
        # program entrypoint
        "main",
    }
)

MODEL_BASE_PRESETS: frozenset[str] = frozenset(
    {
        "BaseModel",
        "pydantic.BaseModel",
        "BaseSettings",
        "pydantic_settings.BaseSettings",
        "TypedDict",
        "typing.TypedDict",
        "typing_extensions.TypedDict",
        "Protocol",
        "typing.Protocol",
        "NamedTuple",
        "typing.NamedTuple",
        "Enum",
        "enum.Enum",
        "StrEnum",
        "enum.StrEnum",
        "IntEnum",
        "enum.IntEnum",
    }
)

DATACLASS_DECORATOR_PRESETS: frozenset[str] = frozenset(
    {
        "dataclass",
        "dataclasses.dataclass",
        "pydantic.dataclasses.dataclass",
    }
)


def is_dunder(name: str) -> bool:
    """True for dunder names like ``__init__`` (treated as lifecycle hooks)."""

    return len(name) > 4 and name.startswith("__") and name.endswith("__")


__all__ = [
    "DATACLASS_DECORATOR_PRESETS",
    "HOOK_NAME_PRESETS",
    "MODEL_BASE_PRESETS",
    "REGISTRY_DECORATOR_PRESETS",
    "is_dunder",
]
