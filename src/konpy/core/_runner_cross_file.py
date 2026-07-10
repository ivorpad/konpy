"""Run-scoped cross-file structure and index cache for predicate evaluation."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TypeVar, cast

from konpy.core._runner_source_cache import _get_or_parse_file_structure
from konpy.core.context import CrossFileScope
from konpy.core.filesystem import FileSystem
from konpy.python_ast.structure import PyFileStructure

_IndexT = TypeVar("_IndexT")


@dataclass
class RunCrossFileIndexCache:
    """Build and cache derived cross-file indexes for a single `run()` call."""

    file_system: FileSystem
    file_structure_cache: dict[str, PyFileStructure]
    source_cache: dict[str, str]
    _indexes: dict[tuple[tuple[str, ...], Hashable], object] = field(default_factory=dict)

    def scope(self, paths: Iterable[str]) -> CrossFileScope:
        """Return a deterministic scope provider for the given effective file set."""
        return _RunnerCrossFileScope(
            paths=tuple(sorted(set(paths))),
            cache=self,
        )

    def _get_or_build(
        self,
        *,
        paths: tuple[str, ...],
        key: Hashable,
        builder: Callable[[Mapping[str, PyFileStructure]], _IndexT],
    ) -> _IndexT:
        cache_key = (paths, key)
        if cache_key not in self._indexes:
            structures = {
                path: _get_or_parse_file_structure(
                    file_path=path,
                    file_system=self.file_system,
                    cache=self.file_structure_cache,
                    source_cache=self.source_cache,
                )
                for path in paths
            }
            self._indexes[cache_key] = builder(structures)

        return cast(_IndexT, self._indexes[cache_key])


@dataclass(frozen=True, kw_only=True)
class _RunnerCrossFileScope:
    paths: tuple[str, ...]
    cache: RunCrossFileIndexCache

    def get_or_build_index(
        self,
        key: Hashable,
        builder: Callable[[Mapping[str, PyFileStructure]], _IndexT],
    ) -> _IndexT:
        return self.cache._get_or_build(paths=self.paths, key=key, builder=builder)


__all__ = ["RunCrossFileIndexCache"]
