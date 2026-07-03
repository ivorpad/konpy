"""Cached source-reading and AST-parsing helpers shared by the runner."""

from __future__ import annotations

from konsistent.core.filesystem import FileSystem
from konsistent.python_ast.parser import parse_file_structure
from konsistent.python_ast.structure import PyFileStructure


def _read_source_with_cache(
    *,
    file_path: str,
    file_system: FileSystem,
    source_cache: dict[str, str],
) -> str:
    cached = source_cache.get(file_path)
    if cached is not None:
        return cached

    source = file_system.read_file(file_path)
    source_cache[file_path] = source
    return source


def _try_read_source_with_cache(
    *,
    file_path: str,
    file_system: FileSystem,
    source_cache: dict[str, str],
) -> str | None:
    try:
        return _read_source_with_cache(
            file_path=file_path,
            file_system=file_system,
            source_cache=source_cache,
        )
    except OSError:
        return None


def _get_or_parse_file_structure(
    *,
    file_path: str,
    file_system: FileSystem,
    cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
) -> PyFileStructure:
    cached = cache.get(file_path)
    if cached is not None:
        return cached

    source = _read_source_with_cache(
        file_path=file_path,
        file_system=file_system,
        source_cache=source_cache,
    )
    structure = parse_file_structure(source, file_path)
    cache[file_path] = structure
    return structure
