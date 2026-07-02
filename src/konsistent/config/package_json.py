from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata, resources
from typing import Literal

PackageJsonLookupFailureKind = Literal[
    "invalid-name",
    "not-installed",
    "missing-json",
    "read-error",
]

DISTRIBUTION_NAME_PATTERN = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
_DISTRIBUTION_NAME_REGEX = re.compile(f"^{DISTRIBUTION_NAME_PATTERN}$")


@dataclass(frozen=True)
class PackageJsonDocument:
    requested_name: str
    distribution_name: str
    raw: str
    location_label: str
    origin_id: str


@dataclass(frozen=True)
class PackageJsonLookupFailure:
    kind: PackageJsonLookupFailureKind
    detail: str | None = None
    top_level_packages: tuple[str, ...] = ()


def is_valid_distribution_name(value: str) -> bool:
    return _DISTRIBUTION_NAME_REGEX.fullmatch(value) is not None


def find_package_konsistent_json(
    value: str,
) -> PackageJsonDocument | PackageJsonLookupFailure:
    if not is_valid_distribution_name(value):
        return PackageJsonLookupFailure(kind="invalid-name")

    try:
        distribution = metadata.distribution(value)
    except metadata.PackageNotFoundError:
        return PackageJsonLookupFailure(kind="not-installed")

    distribution_name = distribution.metadata.get("Name", value)
    top_level_packages = _top_level_import_packages(
        distribution=distribution,
        distribution_name=distribution_name,
    )

    for package_name in top_level_packages:
        resource_result = _read_top_level_resource(
            requested_name=value,
            distribution_name=distribution_name,
            package_name=package_name,
        )
        if isinstance(resource_result, PackageJsonLookupFailure):
            return resource_result
        if resource_result is not None:
            return resource_result

    dist_info_result = _read_dist_info_file(
        requested_name=value,
        distribution=distribution,
        distribution_name=distribution_name,
    )
    if isinstance(dist_info_result, PackageJsonLookupFailure):
        return dist_info_result
    if dist_info_result is not None:
        return dist_info_result

    return PackageJsonLookupFailure(
        kind="missing-json",
        top_level_packages=top_level_packages,
    )


def _top_level_import_packages(
    *,
    distribution: metadata.Distribution,
    distribution_name: str,
) -> tuple[str, ...]:
    try:
        top_level_text = distribution.read_text("top_level.txt")
    except OSError:
        top_level_text = None

    if top_level_text:
        packages = tuple(
            line.strip()
            for line in top_level_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        if packages:
            return packages

    return (distribution_name.replace("-", "_"),)


def _read_top_level_resource(
    *,
    requested_name: str,
    distribution_name: str,
    package_name: str,
) -> PackageJsonDocument | PackageJsonLookupFailure | None:
    location_path = f"{package_name}/konsistent.json"

    try:
        candidate = resources.files(package_name) / "konsistent.json"
    except ModuleNotFoundError:
        return None
    except Exception as error:
        return PackageJsonLookupFailure(
            kind="read-error",
            detail=f"{location_path}: {error}",
        )

    try:
        if not candidate.is_file():
            return None
        raw = candidate.read_text(encoding="utf-8")
    except OSError as error:
        return PackageJsonLookupFailure(
            kind="read-error",
            detail=f"{location_path}: {error}",
        )

    location_label = f"package {location_path}"
    return PackageJsonDocument(
        requested_name=requested_name,
        distribution_name=distribution_name,
        raw=raw,
        location_label=location_label,
        origin_id=_package_origin_id(
            distribution_name=distribution_name,
            location_path=location_path,
        ),
    )


def _read_dist_info_file(
    *,
    requested_name: str,
    distribution: metadata.Distribution,
    distribution_name: str,
) -> PackageJsonDocument | PackageJsonLookupFailure | None:
    files = distribution.files
    if files is None:
        return None

    for package_path in files:
        if package_path.name != "konsistent.json":
            continue
        if not any(part.endswith(".dist-info") for part in package_path.parts):
            continue

        location_path = package_path.as_posix()
        try:
            raw = distribution.locate_file(package_path).read_text(encoding="utf-8")
        except OSError as error:
            return PackageJsonLookupFailure(
                kind="read-error",
                detail=f"{location_path}: {error}",
            )

        location_label = f"distribution file {location_path}"
        return PackageJsonDocument(
            requested_name=requested_name,
            distribution_name=distribution_name,
            raw=raw,
            location_label=location_label,
            origin_id=_package_origin_id(
                distribution_name=distribution_name,
                location_path=location_path,
            ),
        )

    return None


def _package_origin_id(*, distribution_name: str, location_path: str) -> str:
    canonical_name = re.sub(r"[-_.]+", "-", distribution_name).lower()
    return f"package:{canonical_name}:{location_path}"


__all__ = [
    "DISTRIBUTION_NAME_PATTERN",
    "PackageJsonDocument",
    "PackageJsonLookupFailure",
    "PackageJsonLookupFailureKind",
    "find_package_konsistent_json",
    "is_valid_distribution_name",
]
