from __future__ import annotations

from collections.abc import Mapping, Sequence

from wcmatch import glob as wcglob

from konpy.core._filesystem_base import (
    _GLOB_FLAGS,
    FileSystem,
    _normalize_relative_path,
    _parent_paths,
)


class OverlayFileSystem:
    """A `FileSystem` that overlays proposed in-memory content onto a base FS.

    Used by `konpy gate` to check the proposed post-write state of files without
    touching disk. Overlaid paths read back proposed content, count as existing,
    appear in matching globs, and materialize their parent directories.
    """

    def __init__(self, base: FileSystem, overlay: Mapping[str, str]) -> None:
        self._base = base
        self._overlay = {
            _normalize_relative_path(path): content for path, content in overlay.items()
        }
        self._overlay_files = set(self._overlay)
        self._overlay_parents: set[str] = set()
        for path in self._overlay_files:
            self._overlay_parents.update(_parent_paths(path))

    def glob(self, patterns: Sequence[str]) -> list[str]:
        """Return base matches plus matching overlay-only files, preserving order."""
        normalized_patterns = [_normalize_relative_path(pattern) for pattern in patterns]
        base_results = self._base.glob(normalized_patterns)

        seen = set(base_results)
        results = list(base_results)

        for path in sorted(self._overlay_files):
            if path in seen:
                continue
            if self._base.file_exists(path):
                continue
            if wcglob.globmatch(path, normalized_patterns, flags=_GLOB_FLAGS):
                seen.add(path)
                results.append(path)

        return results

    def is_directory(self, path: str) -> bool:
        """Check whether `path` is a directory in the overlaid view."""
        normalized = _normalize_relative_path(path)
        if normalized in self._overlay_files:
            return False
        if normalized == "" or normalized in self._overlay_parents:
            return True
        return self._base.is_directory(normalized)

    def file_exists(self, path: str) -> bool:
        """Check whether `path` exists in the overlaid view."""
        normalized = _normalize_relative_path(path)
        if normalized in self._overlay_files or normalized in self._overlay_parents:
            return True
        return self._base.file_exists(normalized)

    def read_dir(self, path: str) -> list[str]:
        """List direct children from the base plus overlay-only entries."""
        normalized = _normalize_relative_path(path)
        base_entries = self._base.read_dir(normalized)

        seen = set(base_entries)
        overlay_entries: set[str] = set()

        prefix = f"{normalized}/" if normalized else ""
        candidates = self._overlay_files | self._overlay_parents

        for candidate in candidates:
            if candidate == normalized or not candidate.startswith(prefix):
                continue
            if self._base.file_exists(candidate):
                continue

            rest = candidate[len(prefix) :]
            if not rest:
                continue

            child = rest.split("/", 1)[0]
            if child not in seen:
                overlay_entries.add(child)

        return [*base_entries, *sorted(overlay_entries)]

    def read_file(self, path: str) -> str:
        """Read proposed content for overlaid files, otherwise delegate to base."""
        normalized = _normalize_relative_path(path)
        if normalized in self._overlay:
            return self._overlay[normalized]
        return self._base.read_file(normalized)


__all__ = ["OverlayFileSystem"]
