from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

_UNSET = object()


def install_fake_distribution(
    *,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    distribution_name: str,
    import_package: str | None = None,
    package_json: object = _UNSET,
    package_json_text: str | None = None,
    dist_info_json: object = _UNSET,
    dist_info_json_text: str | None = None,
    top_level_text: str | None = None,
    write_top_level: bool = True,
    entry_points: dict[str, dict[str, str]] | None = None,
    modules: dict[str, str] | None = None,
) -> Path:
    site_dir = tmp_path / "site"
    site_dir.mkdir(exist_ok=True)

    import_package = import_package or distribution_name.replace("-", "_")
    top_level = top_level_text if top_level_text is not None else f"{import_package}\n"

    record_entries: list[str] = []

    package_dir = site_dir / import_package
    package_dir.mkdir(parents=True, exist_ok=True)
    init_path = package_dir / "__init__.py"
    init_path.write_text("", encoding="utf-8")
    record_entries.append(init_path.relative_to(site_dir).as_posix())

    for module_name, source in (modules or {}).items():
        module_path = _module_path(package_dir=package_dir, module_name=module_name)
        module_path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_package_inits(package_dir=package_dir, module_path=module_path)
        module_path.write_text(source, encoding="utf-8")
        record_entries.append(module_path.relative_to(site_dir).as_posix())

    if package_json_text is not None or package_json is not _UNSET:
        package_json_path = package_dir / "konsistent.json"
        package_json_path.write_text(
            package_json_text if package_json_text is not None else json.dumps(package_json),
            encoding="utf-8",
        )
        record_entries.append(package_json_path.relative_to(site_dir).as_posix())

    dist_info_dir = site_dir / f"{distribution_name.replace('-', '_')}-1.0.dist-info"
    dist_info_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = dist_info_dir / "METADATA"
    metadata_path.write_text(
        f"Metadata-Version: 2.1\nName: {distribution_name}\nVersion: 1.0\n",
        encoding="utf-8",
    )
    record_entries.append(metadata_path.relative_to(site_dir).as_posix())

    if write_top_level:
        top_level_path = dist_info_dir / "top_level.txt"
        top_level_path.write_text(top_level, encoding="utf-8")
        record_entries.append(top_level_path.relative_to(site_dir).as_posix())

    if entry_points is not None:
        entry_points_path = dist_info_dir / "entry_points.txt"
        entry_points_path.write_text(_format_entry_points(entry_points), encoding="utf-8")
        record_entries.append(entry_points_path.relative_to(site_dir).as_posix())

    if dist_info_json_text is not None or dist_info_json is not _UNSET:
        dist_info_json_path = dist_info_dir / "konsistent.json"
        dist_info_json_path.write_text(
            dist_info_json_text
            if dist_info_json_text is not None
            else json.dumps(dist_info_json),
            encoding="utf-8",
        )
        record_entries.append(dist_info_json_path.relative_to(site_dir).as_posix())

    record_path = dist_info_dir / "RECORD"
    record_entries.append(record_path.relative_to(site_dir).as_posix())
    record_path.write_text(
        "".join(f"{entry},,\n" for entry in record_entries),
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(site_dir))
    for package_name in _top_level_package_names(top_level):
        _drop_imported_package(package_name)
    importlib.invalidate_caches()

    return site_dir


def reusable_convention_package(name: str = "package-must-have-readme") -> dict[str, Any]:
    return {
        "conventionSpecVersion": "v1",
        "conventions": [
            {
                "name": name,
                "description": "Every package must have README.",
                "paths": "packages/{packageName}",
                "must": {"haveFiles": ["README.md"]},
            }
        ],
    }


def raw_config_package(name: str = "base-rule") -> dict[str, Any]:
    return {
        "version": "v1",
        "conventions": [
            {
                "name": name,
                "paths": "packages/{packageName}",
                "must": {"haveFiles": ["README.md"]},
            }
        ],
    }


def _module_path(*, package_dir: Path, module_name: str) -> Path:
    if module_name.endswith(".py") or "/" in module_name:
        return package_dir / module_name

    return package_dir / Path(module_name.replace(".", "/")).with_suffix(".py")


def _ensure_package_inits(*, package_dir: Path, module_path: Path) -> None:
    current = module_path.parent
    while current != package_dir and package_dir in current.parents:
        init_path = current / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")
        current = current.parent


def _format_entry_points(entry_points: dict[str, dict[str, str]]) -> str:
    chunks: list[str] = []
    for group, entries in entry_points.items():
        chunks.append(f"[{group}]\n")
        for name, value in entries.items():
            chunks.append(f"{name} = {value}\n")
        chunks.append("\n")
    return "".join(chunks)


def _drop_imported_package(package_name: str) -> None:
    for module_name in list(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            sys.modules.pop(module_name, None)


def _top_level_package_names(top_level_text: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in top_level_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
