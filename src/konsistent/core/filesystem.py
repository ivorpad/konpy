from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from wcmatch import glob as wcglob

_GLOB_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR


class FileSystem(Protocol):
    """Filesystem access abstraction used by predicates and the runner."""

    def glob(self, patterns: Sequence[str]) -> list[str]:
        """Return paths matching any of `patterns`."""
        ...

    def is_directory(self, path: str) -> bool:
        """Check whether `path` is a directory."""
        ...

    def file_exists(self, path: str) -> bool:
        """Check whether `path` exists."""
        ...

    def read_dir(self, path: str) -> list[str]:
        """List entry names directly under `path`."""
        ...

    def read_file(self, path: str) -> str:
        """Read the text contents of `path`."""
        ...


def _normalize_relative_path(path: str | Path) -> str:
    text = str(path).replace(os.sep, "/")
    if os.altsep is not None:
        text = text.replace(os.altsep, "/")
    if text == ".":
        return ""
    text = text.removeprefix("./")
    if text.endswith("/") and text != "/":
        text = text[:-1]
    return text


normalize_relative_path = _normalize_relative_path


def _parent_paths(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    parents: list[str] = []
    current = ""
    for part in parts:
        current = part if current == "" else f"{current}/{part}"
        parents.append(current)
    return parents


class RealFileSystem:
    """`FileSystem` backed by the actual disk, rooted at `cwd`."""

    def __init__(self, *, cwd: str | Path) -> None:
        self._cwd = Path(cwd)
        self._glob_cache: dict[str, tuple[str, ...]] = {}

    def glob(self, patterns: Sequence[str]) -> list[str]:
        """Return disk paths matching any of `patterns`, cached per pattern set."""
        key = "\x00".join(patterns)
        cached = self._glob_cache.get(key)
        if cached is not None:
            return list(cached)

        raw_results = wcglob.glob(
            list(patterns),
            root_dir=str(self._cwd),
            flags=_GLOB_FLAGS,
        )

        seen: set[str] = set()
        results: list[str] = []
        for raw_path in raw_results:
            normalized = self._normalize_glob_result(raw_path)
            if normalized not in seen:
                seen.add(normalized)
                results.append(normalized)

        self._glob_cache[key] = tuple(results)
        return list(results)

    def is_directory(self, path: str) -> bool:
        """Check whether `path` is a directory on disk."""
        try:
            return self._resolve(path).is_dir()
        except OSError:
            return False

    def file_exists(self, path: str) -> bool:
        """Check whether `path` exists on disk."""
        try:
            return self._resolve(path).exists()
        except OSError:
            return False

    def read_dir(self, path: str) -> list[str]:
        """List entry names directly under `path` on disk."""
        try:
            return [entry.name for entry in self._resolve(path).iterdir()]
        except OSError:
            return []

    def read_file(self, path: str) -> str:
        """Read the text contents of `path` from disk."""
        return self._resolve(path).read_text(encoding="utf-8")

    def _resolve(self, path: str) -> Path:
        return self._cwd / _normalize_relative_path(path)

    def _normalize_glob_result(self, path: str | Path) -> str:
        raw_path = Path(path)
        if raw_path.is_absolute():
            try:
                return _normalize_relative_path(raw_path.relative_to(self._cwd))
            except ValueError:
                return _normalize_relative_path(raw_path)
        return _normalize_relative_path(path)


class FakeFileSystem:
    """In-memory `FileSystem` for tests, seeded with files/directories/contents."""

    def __init__(
        self,
        *,
        glob_results: Mapping[tuple[str, ...], Sequence[str]] | None = None,
        files: Iterable[str] = (),
        directories: Iterable[str] = (),
        contents: Mapping[str, str] | None = None,
    ) -> None:
        self._glob_results = {
            tuple(_normalize_relative_path(pattern) for pattern in patterns): [
                _normalize_relative_path(path) for path in paths
            ]
            for patterns, paths in (glob_results or {}).items()
        }

        content_paths = set(contents or {})
        self._files = {_normalize_relative_path(path) for path in files}
        self._files.update(_normalize_relative_path(path) for path in content_paths)

        self._directories = {_normalize_relative_path(path) for path in directories}
        self._directories.add("")
        for path in self._files | self._directories:
            self._directories.update(_parent_paths(path))

        self._contents = {
            _normalize_relative_path(path): value for path, value in (contents or {}).items()
        }
        self.glob_calls: dict[tuple[str, ...], int] = {}

    def glob(self, patterns: Sequence[str]) -> list[str]:
        """Return seeded paths matching any of `patterns`, recording the call."""
        key = tuple(_normalize_relative_path(pattern) for pattern in patterns)
        self.glob_calls[key] = self.glob_calls.get(key, 0) + 1

        explicit = self._glob_results.get(key)
        if explicit is not None:
            return list(explicit)

        candidates = sorted(path for path in self._files | self._directories if path)
        return [
            candidate
            for candidate in candidates
            if wcglob.globmatch(candidate, list(key), flags=_GLOB_FLAGS)
        ]

    def is_directory(self, path: str) -> bool:
        """Check whether `path` was seeded as a directory."""
        return _normalize_relative_path(path) in self._directories

    def file_exists(self, path: str) -> bool:
        """Check whether `path` was seeded as a file or directory."""
        normalized = _normalize_relative_path(path)
        return normalized in self._files or normalized in self._directories

    def read_dir(self, path: str) -> list[str]:
        """List entry names directly under the seeded directory `path`."""
        normalized = _normalize_relative_path(path)
        if normalized not in self._directories:
            return []

        prefix = f"{normalized}/" if normalized else ""
        children: set[str] = set()

        for candidate in self._files | self._directories:
            if candidate == normalized or not candidate.startswith(prefix):
                continue

            rest = candidate[len(prefix) :]
            if rest:
                children.add(rest.split("/", 1)[0])

        return sorted(children)

    def read_file(self, path: str) -> str:
        """Read the seeded text contents of `path`."""
        normalized = _normalize_relative_path(path)
        try:
            return self._contents[normalized]
        except KeyError as error:
            raise FileNotFoundError(normalized) from error


__all__ = ["FakeFileSystem", "FileSystem", "RealFileSystem", "normalize_relative_path"]
