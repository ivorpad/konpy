"""`konpy report` implementation: the zero-config codebase report.

This is what bare `konpy` runs: unused code, duplication, and coverage over
the current directory with no config required, plus a conventions summary
when konpy.json is present. Exit 1 only when conventions report errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer

from konpy.config.loader import CONFIG_FILENAME
from konpy.core._report_render import render_report
from konpy.core.filesystem import RealFileSystem
from konpy.core.report import assemble_report


def split_exclude_values(values: Sequence[str]) -> list[str]:
    """Split `--exclude` values on top-level commas and whitespace.

    Commas and whitespace inside `{...}` brace alternation are preserved, so
    `**/{tests,docs}/**` stays one pattern while `a,b` becomes two. Empty
    segments are dropped, order is preserved, and duplicates are collapsed.
    """
    patterns: list[str] = []
    for value in values:
        depth = 0
        current: list[str] = []
        for char in value:
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif depth == 0 and (char == "," or char.isspace()):
                patterns.append("".join(current))
                current = []
                continue
            current.append(char)
        patterns.append("".join(current))
    return list(dict.fromkeys(pattern for pattern in patterns if pattern))


def run_report_command(exclude: Sequence[str] | None = None) -> int:
    """Assemble and print the zero-config report for the current directory."""
    cwd = Path.cwd()
    data = assemble_report(
        file_system=RealFileSystem(cwd=cwd),
        config_path=cwd / CONFIG_FILENAME,
        exclude=split_exclude_values(exclude or ()),
    )
    typer.echo(render_report(data))
    return 1 if data.conventions.errors else 0


__all__ = ["run_report_command", "split_exclude_values"]
