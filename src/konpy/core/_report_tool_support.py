"""Shared plumbing for the report's external-tool lanes.

Owns the pieces every lane needs but no lane owns: the subprocess runner
seam, target-venv executable resolution, and the "... and N more" remainder
item appended to a truncated breakdown.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

# A subprocess runner: `subprocess.run` in production, a canned stand-in in
# tests. Kept as a type alias so every lane function shares one signature.
Runner = Callable[..., subprocess.CompletedProcess[str]]


def resolve_tool_executable(root: Path, name: str) -> str:
    """Prefer `root`'s own `.venv` copy of `name` over a bare PATH lookup.

    konpy commonly runs as an isolated tool install (uv tool, pipx) whose
    PATH never includes the target project's `.venv/bin` -- without this, a
    repo pinning ruff as a dev dependency reads as "not installed". Only the
    conventional `.venv` directory is probed; anything else falls back to
    PATH, where an activated environment wins as before.
    """
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    suffix = ".exe" if sys.platform == "win32" else ""
    candidate = root / ".venv" / bin_dir / f"{name}{suffix}"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return name


def run_tool(
    argv: Sequence[str], *, root: Path, timeout: float, runner: Runner
) -> subprocess.CompletedProcess[str]:
    """Run one external tool with the report's standard subprocess settings."""
    return runner(
        list(argv),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def more_items_note(shown: int, total: int) -> tuple[str, ...]:
    """A trailing "... and N more" pseudo-item for a truncated breakdown.

    Empty when nothing was hidden, so callers can always concatenate it.
    """
    hidden = total - shown
    if hidden <= 0:
        return ()
    return (f"... and {hidden} more",)


__all__ = ["Runner", "more_items_note", "resolve_tool_executable", "run_tool"]
