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

_GLOB_METACHARACTERS = frozenset("*?[{")


def split_exclude_values(values: Sequence[str]) -> list[str]:
    """Split `--exclude` values on top-level commas and whitespace.

    Commas and whitespace inside `{...}` brace alternation are preserved, so
    `**/{tests,docs}/**` stays one pattern while `a,b` becomes two. Empty
    segments are dropped, order is preserved, and duplicates are collapsed.

    A pattern with no glob metacharacters is treated as a path prefix and also
    matches everything beneath it, so `--exclude vendor` behaves like
    `--exclude 'vendor/**'` rather than silently matching only the directory
    entry itself.
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

    expanded: list[str] = []
    for pattern in patterns:
        if not pattern:
            continue
        expanded.append(pattern)
        if not _GLOB_METACHARACTERS.intersection(pattern):
            expanded.append(f"{pattern.rstrip('/')}/**")
    return list(dict.fromkeys(expanded))


def _warn_unmatched(file_system: RealFileSystem, patterns: Sequence[str]) -> None:
    """Warn on stderr about `--exclude` patterns that match nothing.

    A misspelled exclude is otherwise indistinguishable from a correct one: the
    report simply comes back unscoped. Prefix-expanded companions (`dir/**`) are
    not reported separately, so one typo yields one warning.
    """
    for pattern in patterns:
        if pattern.endswith("/**") and pattern[: -len("/**")] in patterns:
            continue
        if not file_system.glob([pattern]):
            typer.echo(
                f"konpy report: --exclude pattern matched nothing: {pattern}",
                err=True,
            )


def run_report_command(
    exclude: Sequence[str] | None = None, *, include_vendored: bool = False
) -> int:
    """Assemble and print the zero-config report for the current directory."""
    cwd = Path.cwd()
    file_system = RealFileSystem(cwd=cwd)
    patterns = split_exclude_values(exclude or ())
    _warn_unmatched(file_system, patterns)
    data = assemble_report(
        file_system=file_system,
        config_path=cwd / CONFIG_FILENAME,
        exclude=patterns,
        include_vendored=include_vendored,
    )
    typer.echo(render_report(data))
    return 1 if data.conventions.errors else 0


__all__ = ["run_report_command", "split_exclude_values"]
