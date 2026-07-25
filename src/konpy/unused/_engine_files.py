"""File collection, parsing, and repo-layout helpers for the unused engine.

Split out of `konpy.unused.engine` (which orchestrates the run) to keep that
module under the project's per-module line limit.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from konpy.core.filesystem import FileSystem


def _local_module_roots(paths: set[str]) -> frozenset[str]:
    """Import roots that resolve inside the repo, so they are not third-party.

    Each path contributes its first segment (`pkg/mod.py` -> `pkg`,
    `mod.py` -> `mod`) plus its topmost package directory — the first
    ancestor carrying an `__init__.py` — so any layout root (`src/`,
    `source/`, `packages/<name>/src/`) still yields the importable package
    name. `src/`/`lib/` second segments are added unconditionally to cover
    namespace packages without `__init__.py`.
    """
    path_set = set(paths)
    roots: set[str] = set()
    for path in paths:
        parts = path.split("/")
        roots.add(parts[0].removesuffix(".py"))
        if len(parts) > 1 and parts[0] in ("src", "lib"):
            roots.add(parts[1].removesuffix(".py"))
        for depth in range(len(parts) - 1):
            if "/".join([*parts[: depth + 1], "__init__.py"]) in path_set:
                roots.add(parts[depth])
                break
    return frozenset(roots)


def _python_files(file_system: FileSystem, patterns: Sequence[str]) -> list[str]:
    if not patterns:
        return []
    results: list[str] = []
    for path in file_system.glob(list(patterns)):
        if path.endswith(".py") and not file_system.is_directory(path):
            results.append(path)
    return results


def _entrypoint_texts(
    file_system: FileSystem,
    patterns: Sequence[str],
    *,
    source_cache: dict[str, str] | None = None,
    excluded: set[str] | None = None,
) -> list[str]:
    if not patterns:
        return []
    texts: list[str] = []
    for path in sorted(set(file_system.glob(list(patterns))) - (excluded or set())):
        if file_system.is_directory(path):
            continue
        try:
            texts.append(_read_source(file_system, path, source_cache=source_cache))
        except OSError:
            continue
    return texts


def _parse(
    file_system: FileSystem,
    path: str,
    *,
    source_cache: dict[str, str] | None = None,
) -> ast.Module | None:
    try:
        source = _read_source(file_system, path, source_cache=source_cache)
    except OSError:
        return None
    try:
        return ast.parse(source, filename=path)
    except SyntaxError:
        return None


def _read_source(
    file_system: FileSystem,
    path: str,
    *,
    source_cache: dict[str, str] | None,
) -> str:
    if source_cache is None:
        return file_system.read_file(path)

    cached = source_cache.get(path)
    if cached is not None:
        return cached

    source = file_system.read_file(path)
    source_cache[path] = source
    return source


__all__: list[str] = []
