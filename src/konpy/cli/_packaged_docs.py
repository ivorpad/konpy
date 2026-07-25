"""Bundled reference-doc access for the `konpy` CLI.

Reads `docs/reference/*.md` from the source tree during development and from
the `konpy/_docs/reference/` package data (force-included into the wheel)
when installed. Shared by `konpy docs` and the extract-rules prompt builder.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from konpy.config.errors import Err, Ok, Result

_PACKAGED_REFERENCE_ROOT = "_docs/reference"


def _source_tree_reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "docs/reference"


def read_reference_doc(topic: str) -> Result[str]:
    """Read `docs/reference/<topic>.md` from the source tree or package data."""
    filename = f"{topic}.md"

    source_tree_path = _source_tree_reference_dir() / filename
    try:
        if source_tree_path.is_file():
            return Ok(source_tree_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    try:
        text = (
            resources.files("konpy")
            .joinpath(f"{_PACKAGED_REFERENCE_ROOT}/{filename}")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return Err(f"Could not read reference doc docs/reference/{filename}.")

    return Ok(text)


def available_reference_topics() -> list[str]:
    """List bundled reference-doc topics (`.md` basenames), sorted."""
    topics: set[str] = set()

    source_dir = _source_tree_reference_dir()
    try:
        if source_dir.is_dir():
            topics.update(path.stem for path in source_dir.glob("*.md"))
    except OSError:
        pass

    if not topics:
        try:
            packaged = resources.files("konpy").joinpath(_PACKAGED_REFERENCE_ROOT)
            topics.update(
                entry.name.removesuffix(".md")
                for entry in packaged.iterdir()
                if entry.name.endswith(".md")
            )
        except (FileNotFoundError, ModuleNotFoundError, OSError):
            pass

    return sorted(topics)


__all__ = [
    "available_reference_topics",
    "read_reference_doc",
]
