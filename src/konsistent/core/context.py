from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass

from konsistent.core.filesystem import FileSystem
from konsistent.core.path_matcher import MatchedPath
from konsistent.core.placeholders import PlaceholderValue
from konsistent.core.templates import resolve_template


@dataclass(frozen=True, kw_only=True)
class PredicateContext:
    """Resolved matched-path state passed to predicates during evaluation."""

    path: str
    placeholders: Mapping[str, PlaceholderValue]
    file_system: FileSystem
    base_path: str

    def resolve_template(self, template: str) -> str:
        """Resolve `template` against this context's placeholders."""
        return resolve_template(template, self.placeholders)

    def file_exists(self, relative_path: str) -> bool:
        """Check whether `relative_path` exists relative to `base_path`."""
        return self.file_system.file_exists(_join_relative(self.base_path, relative_path))

    def read_dir(self, relative_path: str) -> list[str]:
        """List entries under `relative_path` relative to `base_path`."""
        return self.file_system.read_dir(_join_relative(self.base_path, relative_path))


def build_context(*, matched: MatchedPath, file_system: FileSystem) -> PredicateContext:
    """Build a `PredicateContext` for a matched path, deriving its base directory."""
    base_path = matched.path if file_system.is_directory(matched.path) else posixpath.dirname(
        matched.path
    )
    return PredicateContext(
        path=matched.path,
        placeholders=matched.placeholders,
        file_system=file_system,
        base_path=base_path,
    )


def _join_relative(base_path: str, relative_path: str) -> str:
    if base_path == "":
        return relative_path
    return posixpath.join(base_path, relative_path)


__all__ = ["PredicateContext", "build_context"]
