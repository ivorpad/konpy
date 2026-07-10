from __future__ import annotations

import os
from collections.abc import Sequence
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


__all__ = [
    "FileSystem",
    "normalize_relative_path",
]
