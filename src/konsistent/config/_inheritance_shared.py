from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from konsistent.config.package_json import PackageJsonDocument, PackageJsonLookupFailure


@dataclass(frozen=True)
class _ConfigOrigin:
    id: str
    label: str
    local_dir: Path | None


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


def _contains_origin(*, stack: tuple[_ConfigOrigin, ...], origin: _ConfigOrigin) -> bool:
    return any(entry.id == origin.id for entry in stack)


def _format_cycle(stack: tuple[_ConfigOrigin, ...], repeated_origin: _ConfigOrigin) -> str:
    start_index = next(
        index for index, origin in enumerate(stack) if origin.id == repeated_origin.id
    )
    cycle = (*stack[start_index:], repeated_origin)
    return " -> ".join(origin.label for origin in cycle)


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
