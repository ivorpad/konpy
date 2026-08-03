"""Opt-in `ruff check` invocation against `konpy gate`'s proposed overlay content."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from shutil import which

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from konpy.config.errors import Err, Ok, Result
from konpy.core.diagnostics import Diagnostic, create_diagnostic

__all__ = ["RUFF_CONVENTION_NAME", "ruff_available", "run_ruff_on_overlay"]

RUFF_CONVENTION_NAME = "ruff"
_RUFF_TIMEOUT_SECONDS = 30


class _RuffLocation(BaseModel):
    """The `location`/`end_location` object in ruff's `--output-format json`."""

    model_config = ConfigDict(extra="ignore")

    row: int | None = None
    column: int | None = None


class _RuffFix(BaseModel):
    """The `fix` object in ruff's `--output-format json`, when a fix exists."""

    model_config = ConfigDict(extra="ignore")

    message: str | None = None


class _RuffFinding(BaseModel):
    """One element of ruff's `--output-format json` array."""

    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    message: str = ""
    location: _RuffLocation = Field(default_factory=_RuffLocation)
    fix: _RuffFix | None = None


_FINDINGS_ADAPTER = TypeAdapter(list[_RuffFinding])


def ruff_available() -> bool:
    """Return whether a `ruff` executable is discoverable on `PATH`."""
    return which("ruff") is not None


def run_ruff_on_overlay(
    overlay: Mapping[str, str],
    *,
    cwd: Path,
) -> Result[list[Diagnostic]]:
    """Run `ruff check` against each `.py` overlay path's proposed content.

    One `ruff check --stdin-filename <path> --output-format json -`
    subprocess per target, so ruff resolves the target repo's own config
    (`pyproject.toml`/`ruff.toml`, discovered from `cwd`) exactly as it would
    for a real on-disk file at that path. Findings come back as
    error-severity `Diagnostic`s under the `ruff` convention name, with the
    rule code as `predicate_name` and the fix message (if any) as `fix_hint`.
    Non-`.py` overlay paths are ignored.
    """
    diagnostics: list[Diagnostic] = []
    for path in sorted(path for path in overlay if path.endswith(".py")):
        result = _run_ruff_on_one(path=path, content=overlay[path], cwd=cwd)
        if isinstance(result, Err):
            return result
        diagnostics.extend(result.value)
    return Ok(diagnostics)


def _run_ruff_on_one(*, path: str, content: str, cwd: Path) -> Result[list[Diagnostic]]:
    try:
        completed = subprocess.run(
            ["ruff", "check", "--stdin-filename", path, "--output-format", "json", "-"],
            input=content,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_RUFF_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Err(f"ruff invocation failed: {error}")

    # Exit 0 = clean, 1 = findings reported as JSON on stdout; any other code
    # means ruff itself failed (bad invocation, internal error) rather than
    # having something to report.
    if completed.returncode not in (0, 1):
        detail = completed.stderr.strip() or f"ruff exited {completed.returncode}"
        return Err(f"ruff check failed: {detail}")

    stdout = completed.stdout.strip()
    if not stdout:
        return Ok([])

    try:
        findings = _FINDINGS_ADAPTER.validate_json(stdout)
    except ValidationError as error:
        return Err(f"could not parse ruff output: {error}")

    return Ok([_diagnostic_for(path=path, finding=finding) for finding in findings])


def _diagnostic_for(*, path: str, finding: _RuffFinding) -> Diagnostic:
    return create_diagnostic(
        file_path=path,
        predicate_name=finding.code or "ruff",
        message=finding.message,
        convention_name=RUFF_CONVENTION_NAME,
        line=finding.location.row,
        column=finding.location.column,
        severity="error",
        fix_hint=finding.fix.message if finding.fix is not None else None,
    )
