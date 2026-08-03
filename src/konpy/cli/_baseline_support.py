"""Shared baseline path resolution and file I/O for `check` and `gate`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from konpy.config.errors import Err, Ok, Result
from konpy.core.baseline import BaselineData, build_baseline, load_baseline, serialize_baseline
from konpy.core.diagnostics import Diagnostic

DEFAULT_BASELINE_FILENAME = "konpy.baseline.json"

__all__ = [
    "DEFAULT_BASELINE_FILENAME",
    "RaisedBaselineEntry",
    "compute_raised_entries",
    "format_baseline_written_message",
    "format_raised_warning",
    "read_baseline_if_present",
    "resolve_baseline_path",
    "write_baseline_file",
]


def resolve_baseline_path(*, baseline: str | None, config_path: str | None) -> Path:
    """Resolve the baseline file path.

    `--baseline` wins outright. Otherwise the default is
    `konpy.baseline.json` next to the resolved config file -- `config_path`'s
    directory when given, else the current working directory, mirroring
    `load_config_runtime`'s own default-config resolution.
    """
    if baseline is not None:
        return Path(baseline)

    config_dir = Path(config_path).parent if config_path is not None else Path.cwd()
    return config_dir / DEFAULT_BASELINE_FILENAME


def read_baseline_if_present(path: Path) -> Result[BaselineData | None]:
    """Load `path` as a baseline, or `Ok(None)` when no file exists there.

    A malformed baseline file is a hard error, never silently ignored --
    the same treatment `load_config_runtime` gives an invalid `konpy.json`.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return Ok(None)

    try:
        return Ok(load_baseline(text))
    except ValueError as error:
        return Err(f"Invalid baseline ({path}): {error}")


@dataclass(frozen=True, kw_only=True)
class RaisedBaselineEntry:
    """A `(file, convention)` key whose recorded count went up on rewrite."""

    file_path: str
    convention_name: str
    previous_count: int
    new_count: int


def compute_raised_entries(
    *,
    previous: BaselineData | None,
    new: BaselineData,
) -> list[RaisedBaselineEntry]:
    """Diff `previous` against `new`, returning every key whose count rose.

    Empty when `previous` is `None`: a first-ever `--write-baseline` has
    nothing to compare against, so it never reports a raise. A key present
    in only one side is treated as recorded `0` on the other, so a
    brand-new `(file, convention)` entry counts as a raise from `0` -- the
    baseline floor should only ever move down, never up, without saying so.
    """
    if previous is None:
        return []

    keys = {
        (file_path, convention_name)
        for file_path, conventions in previous.entries.items()
        for convention_name in conventions
    }
    keys.update(
        (file_path, convention_name)
        for file_path, conventions in new.entries.items()
        for convention_name in conventions
    )

    raised: list[RaisedBaselineEntry] = []
    for file_path, convention_name in sorted(keys):
        previous_count = previous.entries.get(file_path, {}).get(convention_name, 0)
        new_count = new.entries.get(file_path, {}).get(convention_name, 0)
        if new_count > previous_count:
            raised.append(
                RaisedBaselineEntry(
                    file_path=file_path,
                    convention_name=convention_name,
                    previous_count=previous_count,
                    new_count=new_count,
                )
            )

    return raised


def format_raised_warning(entry: RaisedBaselineEntry) -> str:
    """Render the loud, never-silent notice for one raised baseline entry."""
    return (
        f"baseline: raised {entry.file_path}/{entry.convention_name} "
        f"from {entry.previous_count} to {entry.new_count}"
    )


def write_baseline_file(*, path: Path, diagnostics: list[Diagnostic]) -> BaselineData:
    """Build a fresh baseline from `diagnostics` and write it to `path`."""
    data = build_baseline(diagnostics)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_baseline(data), encoding="utf-8")
    return data


def format_baseline_written_message(*, data: BaselineData, path: Path) -> str:
    """Render the `--write-baseline` recording-mode confirmation line."""
    violation_count = sum(sum(conventions.values()) for conventions in data.entries.values())
    file_count = len(data.entries)
    violation_word = "violation" if violation_count == 1 else "violations"
    file_word = "file" if file_count == 1 else "files"
    return (
        f"Baseline written: {violation_count} {violation_word} across "
        f"{file_count} {file_word} -> {path}"
    )
