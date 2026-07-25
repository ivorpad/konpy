"""`konpy report` implementation: the zero-config codebase report.

This is what bare `konpy` runs: unused code, duplication, and coverage over
the current directory with no config required, plus a conventions summary
when konpy.json is present. Exit 1 only when conventions report errors.
"""

from __future__ import annotations

from pathlib import Path

import typer

from konpy.config.loader import CONFIG_FILENAME
from konpy.core._report_render import render_report
from konpy.core.filesystem import RealFileSystem
from konpy.core.report import assemble_report


def run_report_command() -> int:
    """Assemble and print the zero-config report for the current directory."""
    cwd = Path.cwd()
    data = assemble_report(
        file_system=RealFileSystem(cwd=cwd),
        config_path=cwd / CONFIG_FILENAME,
    )
    typer.echo(render_report(data))
    return 1 if data.conventions.errors else 0


__all__ = ["run_report_command"]
