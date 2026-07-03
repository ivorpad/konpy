from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from konpy.config.errors import Err, Ok, Result, format_validation_error
from konpy.config.package_json import (
    PackageJsonDocument,
    PackageJsonLookupFailure,
    find_package_konpy_json,
)
from konpy.config.schema import ReusableConventionsPackageV1, ReusableConventionV1

if TYPE_CHECKING:
    # konpy.predicates.registry imports konpy.config.schema at module
    # level, so importing it unconditionally here would cycle back through
    # this package's __init__; PredicateRegistry is only used in annotations.
    from konpy.predicates.registry import PredicateRegistry

SourceKind = Literal["path", "package", "empty"]
SourceMap = dict[str, dict[str, ReusableConventionV1]]


def classify_source(value: str) -> SourceKind:
    """Classify a conventionSources value as a filesystem path, a package name, or empty."""
    if value.strip() == "":
        return "empty"
    if value.startswith(".") or Path(value).is_absolute():
        return "path"
    return "package"


def resolve_sources(
    *,
    convention_sources: Mapping[str, str],
    config_dir: str | Path,
    predicate_registry: PredicateRegistry | None = None,
) -> Result[SourceMap]:
    """Load and validate every conventionSources entry into a prefix-to-conventions map."""
    source_map: SourceMap = {}

    for prefix, value in convention_sources.items():
        kind = classify_source(value)

        if kind == "empty":
            return Err(f'Convention source "{prefix}" has empty value.')

        if kind == "package":
            loaded = _load_from_package(
                prefix=prefix,
                value=value,
                predicate_registry=predicate_registry,
            )
        else:
            loaded = _load_from_path(
                prefix=prefix,
                value=value,
                config_dir=Path(config_dir),
                predicate_registry=predicate_registry,
            )

        if isinstance(loaded, Err):
            return loaded

        package = loaded.value
        source_map[prefix] = {convention.name: convention for convention in package.conventions}

    return Ok(source_map)


def _load_from_package(
    *,
    prefix: str,
    value: str,
    predicate_registry: PredicateRegistry | None,
) -> Result[ReusableConventionsPackageV1]:
    lookup = find_package_konpy_json(value)
    if isinstance(lookup, PackageJsonLookupFailure):
        return Err(_format_package_lookup_error(prefix=prefix, value=value, failure=lookup))

    return _parse_and_validate_package_document(
        prefix=prefix,
        value=value,
        document=lookup,
        predicate_registry=predicate_registry,
    )


def _format_package_lookup_error(
    *,
    prefix: str,
    value: str,
    failure: PackageJsonLookupFailure,
) -> str:
    source = f'Convention source "{prefix}" → "{value}": '

    if failure.kind == "invalid-name":
        return (
            f"{source}invalid Python distribution name. Bare package sources must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
        )

    if failure.kind == "not-installed":
        return (
            f"{source}installed Python distribution not found. Install it or use a local "
            "path in conventionSources."
        )

    if failure.kind == "missing-json":
        return (
            f"{source}installed Python distribution does not contain konpy.json. "
            f"Looked for {_format_top_level_lookup(failure.top_level_packages)} and a "
            "distribution file named konpy.json."
        )

    detail = f" {failure.detail}" if failure.detail else ""
    return f"{source}could not read installed Python distribution data:{detail}."


def _format_top_level_lookup(top_level_packages: tuple[str, ...]) -> str:
    if len(top_level_packages) == 1:
        return f"{top_level_packages[0]}/konpy.json"
    if top_level_packages:
        return "one of " + ", ".join(
            f"{package_name}/konpy.json" for package_name in top_level_packages
        )
    return "<top-level import package>/konpy.json"


def _parse_and_validate_package_document(
    *,
    prefix: str,
    value: str,
    document: PackageJsonDocument,
    predicate_registry: PredicateRegistry | None,
) -> Result[ReusableConventionsPackageV1]:
    return _parse_and_validate(
        prefix=prefix,
        source_label=f'"{value}"',
        location_label=document.location_label,
        raw=document.raw,
        predicate_registry=predicate_registry,
    )


def _load_from_path(
    *,
    prefix: str,
    value: str,
    config_dir: Path,
    predicate_registry: PredicateRegistry | None,
) -> Result[ReusableConventionsPackageV1]:
    resolved_path = (config_dir / value).resolve()

    try:
        raw = resolved_path.read_text(encoding="utf-8")
    except OSError:
        return Err(
            f'Convention source "{prefix}" → "{value}": could not read file at '
            f"{resolved_path}."
        )

    return _parse_and_validate(
        prefix=prefix,
        source_label=f'"{value}"',
        location_label=str(resolved_path),
        raw=raw,
        predicate_registry=predicate_registry,
    )


def _parse_and_validate(
    *,
    prefix: str,
    source_label: str,
    location_label: str,
    raw: str,
    predicate_registry: PredicateRegistry | None,
) -> Result[ReusableConventionsPackageV1]:
    try:
        json_value = json.loads(raw)
    except json.JSONDecodeError:
        return Err(
            f'Convention source "{prefix}" → {source_label}: malformed JSON at '
            f"{location_label}."
        )

    try:
        package = ReusableConventionsPackageV1.model_validate(
            json_value,
            context=_validation_context(predicate_registry),
        )
    except ValidationError as error:
        issues = format_validation_error(error)
        return Err(
            f'Convention source "{prefix}" → {source_label}: invalid '
            f"reusable-convention package at {location_label}:\n{issues}"
        )

    return Ok(package)


def _validation_context(
    predicate_registry: PredicateRegistry | None,
) -> dict[str, PredicateRegistry] | None:
    if predicate_registry is None:
        return None
    return predicate_registry.validation_context()


__all__ = ["SourceKind", "SourceMap", "classify_source", "resolve_sources"]
