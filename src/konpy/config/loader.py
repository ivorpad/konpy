from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from konpy.config.errors import Err, Ok, Result, format_validation_error
from konpy.config.inheritance import collect_config_plugins, resolve_config_inheritance
from konpy.config.placeholder_validator import DECLARATION_REGEX, validate_placeholders
from konpy.config.plugin_loader import load_plugin_registry
from konpy.config.reference_expander import expand_references
from konpy.config.schema import ConfigV1, ConventionV1, RawConfigV1
from konpy.config.source_resolver import resolve_sources
from konpy.predicates.registry import PredicateRegistry

CONFIG_FILENAME = "konpy.json"

_CONFIG_PACKAGE_UNSUPPORTED_ERROR = (
    "--config-package is not supported by the Python port. Use --config-path with a "
    "local konpy.json file."
)


@dataclass(frozen=True, kw_only=True)
class LoadedConfig:
    """A validated config paired with the predicate registry it was resolved against."""

    config: ConfigV1
    predicate_registry: PredicateRegistry


def path_declared_names(paths: str | Sequence[str]) -> set[str]:
    """Collect the {name} placeholder names declared by a convention's path pattern(s)."""
    declared: set[str] = set()
    entries = [paths] if isinstance(paths, str) else paths

    for entry in entries:
        for match in DECLARATION_REGEX.finditer(entry):
            declared.add(match.group(1))

    return declared


def apply_cli_placeholders(
    *,
    conventions: Sequence[ConventionV1],
    identifiers: Sequence[str],
    cli_placeholders: Mapping[str, str],
) -> Result[list[ConventionV1]]:
    """Merge --placeholder CLI values into each convention's placeholders, rejecting conflicts."""
    if len(cli_placeholders) == 0:
        return Ok(list(conventions))

    errors: list[str] = []
    next_conventions: list[ConventionV1] = []

    for index, convention in enumerate(conventions):
        identifier = identifiers[index] if index < len(identifiers) else f"conventions[{index}]"
        declared = path_declared_names(convention.paths)

        for name, value in cli_placeholders.items():
            if name in declared:
                errors.append(
                    f'--placeholder "{name}:{value}" conflicts with convention "{identifier}" '
                    f'which captures "{{{name}}}" from paths. CLI placeholders may only '
                    "override values in placeholders, not path-determined ones."
                )

        placeholders = {**(convention.placeholders or {}), **dict(cli_placeholders)}
        next_conventions.append(convention.model_copy(update={"placeholders": placeholders}))

    if errors:
        return Err("\n".join(errors))

    return Ok(next_conventions)


def load_config_runtime(
    *,
    cli_placeholders: Mapping[str, str] | None = None,
    config_package: str | None = None,
    config_path: str | Path | None = None,
) -> Result[LoadedConfig]:
    """Load, parse, and validate konpy.json into a LoadedConfig with its predicate registry."""
    if config_path is not None and config_package is not None:
        return Err("Cannot use --config-path and --config-package together. Pass only one.")

    if config_package is not None:
        return Err(_CONFIG_PACKAGE_UNSUPPORTED_ERROR)

    file_path = Path(config_path) if config_path is not None else Path.cwd() / CONFIG_FILENAME

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return Err(
            f"Could not read config file: {file_path}\n"
            "Run 'konpy init' to create one, or 'konpy docs configuration' "
            "for the config reference."
        )

    try:
        json_value = json.loads(raw)
    except json.JSONDecodeError:
        return Err(f"Invalid JSON in config file: {file_path}")

    if not isinstance(json_value, Mapping):
        return Err(f"Invalid config ({file_path}):\n  - : Input should be an object")

    plugins_result = collect_config_plugins(raw=json_value, config_path=file_path)
    if isinstance(plugins_result, Err):
        return Err(plugins_result.error)

    registry_result = load_plugin_registry(plugins=plugins_result.value)
    if isinstance(registry_result, Err):
        return Err(registry_result.error)

    predicate_registry = registry_result.value

    inheritance_result = resolve_config_inheritance(
        raw=json_value,
        config_path=file_path,
        predicate_registry=predicate_registry,
    )
    if isinstance(inheritance_result, Err):
        return Err(inheritance_result.error)

    try:
        parsed = RawConfigV1.model_validate(
            inheritance_result.value,
            context=predicate_registry.validation_context(),
        )
    except ValidationError as error:
        return Err(f"Invalid config ({file_path}):\n{format_validation_error(error)}")

    sources_result = resolve_sources(
        convention_sources=parsed.conventionSources or {},
        config_dir=file_path.parent,
        predicate_registry=predicate_registry,
    )
    if isinstance(sources_result, Err):
        return sources_result

    expansion_result = expand_references(
        conventions=parsed.conventions,
        source_map=sources_result.value,
        predicate_registry=predicate_registry,
    )
    if isinstance(expansion_result, Err):
        return Err(expansion_result.error)

    cli_merge = apply_cli_placeholders(
        conventions=expansion_result.value.conventions,
        identifiers=expansion_result.value.identifiers,
        cli_placeholders=cli_placeholders or {},
    )
    if isinstance(cli_merge, Err):
        return cli_merge

    placeholder_result = validate_placeholders(
        conventions=cli_merge.value,
        identifiers=expansion_result.value.identifiers,
    )
    if isinstance(placeholder_result, Err):
        return Err(placeholder_result.error)

    config_data = parsed.model_dump(by_alias=True, exclude_none=True)
    config_data.pop("extends", None)
    config_data.pop("disable", None)
    config_data["conventions"] = [
        convention.model_dump(by_alias=True, exclude_none=True) for convention in cli_merge.value
    ]

    try:
        config = ConfigV1.model_validate(
            config_data,
            context=predicate_registry.validation_context(),
        )
    except ValidationError as error:
        return Err(f"Invalid config ({file_path}):\n{format_validation_error(error)}")

    return Ok(LoadedConfig(config=config, predicate_registry=predicate_registry))


def load_config(
    *,
    cli_placeholders: Mapping[str, str] | None = None,
    config_package: str | None = None,
    config_path: str | Path | None = None,
) -> Result[ConfigV1]:
    """Load konpy.json and return just its validated ConfigV1, discarding the registry."""
    loaded = load_config_runtime(
        cli_placeholders=cli_placeholders,
        config_package=config_package,
        config_path=config_path,
    )
    if isinstance(loaded, Err):
        return loaded

    return Ok(loaded.value.config)


__all__ = [
    "CONFIG_FILENAME",
    "LoadedConfig",
    "apply_cli_placeholders",
    "load_config",
    "load_config_runtime",
    "path_declared_names",
]
