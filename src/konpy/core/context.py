from __future__ import annotations

import posixpath
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Protocol, TypeVar

from konpy.core.filesystem import FileSystem
from konpy.core.path_matcher import MatchedPath
from konpy.core.placeholders import PlaceholderValue
from konpy.core.templates import resolve_template
from konpy.python_ast.structure import PyFileStructure

_IndexT = TypeVar("_IndexT")


class CrossFileScope(Protocol):
    """Run-scoped access to structures and derived indexes for a block's file set."""

    paths: tuple[str, ...]

    def get_or_build_index(
        self,
        key: Hashable,
        builder: Callable[[Mapping[str, PyFileStructure]], _IndexT],
    ) -> _IndexT:
        """Return a cached index for this scope and canonical option key."""
        ...


@dataclass(frozen=True, kw_only=True)
class PredicateContext:
    """Resolved matched-path state passed to predicates during evaluation."""

    path: str
    placeholders: Mapping[str, PlaceholderValue]
    file_system: FileSystem
    base_path: str
    cross_file: CrossFileScope | None = None

    def resolve_template(self, template: str) -> str:
        """Resolve `template` against this context's placeholders."""
        return resolve_template(template, self.placeholders)

    def file_exists(self, relative_path: str) -> bool:
        """Check whether `relative_path` exists relative to `base_path`."""
        return self.file_system.file_exists(_join_relative(self.base_path, relative_path))

    def read_dir(self, relative_path: str) -> list[str]:
        """List entries under `relative_path` relative to `base_path`."""
        return self.file_system.read_dir(_join_relative(self.base_path, relative_path))


def build_context(
    *,
    matched: MatchedPath,
    file_system: FileSystem,
    cross_file: CrossFileScope | None = None,
) -> PredicateContext:
    """Build a `PredicateContext` for a matched path, deriving its base directory."""
    base_path = matched.path if file_system.is_directory(matched.path) else posixpath.dirname(
        matched.path
    )
    return PredicateContext(
        path=matched.path,
        placeholders=matched.placeholders,
        file_system=file_system,
        base_path=base_path,
        cross_file=cross_file,
    )


def _join_relative(base_path: str, relative_path: str) -> str:
    if base_path == "":
        return relative_path
    return posixpath.join(base_path, relative_path)


__all__ = ["CrossFileScope", "PredicateContext", "build_context"]
