"""Brownfield adoption: record existing violations, fail only on new ones.

A baseline is a JSON document mapping `file_path -> convention_name ->
recorded_count`. `apply_baseline` demotes up to `recorded_count` diagnostics
per `(file, convention)` group -- deterministically, by sorting the group's
diagnostics -- leaving anything beyond that count in the fail-normally set
as a genuinely new violation. This mirrors `core.suppressions`'s
post-evaluation filtering seam: `core.runner.run()` applies suppressions
first, then applies the baseline to whatever survives.

This module is presentation-free: it produces data (`BaselineApplication`,
`BaselineStaleEntry`) for a caller to render, never diagnostics or warnings
of its own.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from konpy.core.diagnostics import Diagnostic

BASELINE_VERSION = "v1"

_TOP_LEVEL_KEYS = {"baselineVersion", "entries"}


@dataclass(frozen=True, kw_only=True)
class BaselineData:
    """A loaded baseline: recorded violation counts per file and convention.

    `entries` maps a repo-relative, forward-slash file path (exactly as
    `Diagnostic.file_path` renders it) to a mapping of convention name to
    the recorded violation count for that file.
    """

    baseline_version: str
    entries: dict[str, dict[str, int]]


@dataclass(frozen=True, kw_only=True)
class BaselinedDiagnostic:
    """A diagnostic demoted by the baseline, and the key it was consumed against."""

    diagnostic: Diagnostic
    file_path: str
    convention_name: str


@dataclass(frozen=True, kw_only=True)
class BaselineStaleEntry:
    """A baseline entry whose recorded count exceeds what is currently found.

    Emitted when a `(file, convention)` group in the baseline has fewer
    matching diagnostics now than when it was recorded -- including zero,
    when the file is absent from the current diagnostics entirely. Data
    only; rendering (e.g. as a hygiene warning) is a caller concern.
    """

    file_path: str
    convention_name: str
    recorded_count: int
    found_count: int


@dataclass(frozen=True, kw_only=True)
class BaselineApplication:
    """The outcome of applying a `BaselineData` to a diagnostic list."""

    remaining: list[Diagnostic] = field(default_factory=list)
    baselined: list[BaselinedDiagnostic] = field(default_factory=list)
    stale_entries: list[BaselineStaleEntry] = field(default_factory=list)


def load_baseline(text: str) -> BaselineData:
    """Parse a baseline JSON document into `BaselineData`.

    Raises `ValueError` with a clear message when: the text is not valid
    JSON; the top level is not a JSON object; the top level carries keys
    other than `baselineVersion`/`entries`; `baselineVersion` is missing or
    not exactly `"v1"`; `entries` is present but not an object of objects;
    or any recorded count is not a non-negative integer (bools and numeric
    strings are rejected -- only `int` is accepted).
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid baseline: not valid JSON ({error})") from error

    if not isinstance(raw, dict):
        raise ValueError("Invalid baseline: expected a JSON object at the top level")

    unknown_keys = sorted(set(raw) - _TOP_LEVEL_KEYS)
    if unknown_keys:
        raise ValueError(f"Invalid baseline: unknown top-level key(s) {unknown_keys}")

    version = raw.get("baselineVersion")
    if version != BASELINE_VERSION:
        raise ValueError(
            f'Invalid baseline: expected baselineVersion "{BASELINE_VERSION}", '
            f"found {version!r}"
        )

    entries_raw = raw.get("entries", {})
    if not isinstance(entries_raw, dict):
        raise ValueError('Invalid baseline: "entries" must be an object')

    entries: dict[str, dict[str, int]] = {}
    for file_path, conventions in entries_raw.items():
        if not isinstance(file_path, str):
            raise ValueError("Invalid baseline: entry keys must be strings")
        entries[file_path] = _load_convention_counts(
            file_path=file_path,
            conventions=conventions,
        )

    return BaselineData(baseline_version=version, entries=entries)


def _load_convention_counts(*, file_path: str, conventions: object) -> dict[str, int]:
    if not isinstance(conventions, dict):
        raise ValueError(f'Invalid baseline: entries["{file_path}"] must be an object')

    counts: dict[str, int] = {}
    for convention_name, count in conventions.items():
        if not isinstance(convention_name, str):
            raise ValueError(f'Invalid baseline: entries["{file_path}"] keys must be strings')
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(
                f'Invalid baseline: entries["{file_path}"]["{convention_name}"] must be a '
                "non-negative integer"
            )
        counts[convention_name] = count

    return counts


def serialize_baseline(data: BaselineData) -> str:
    """Render `BaselineData` as stable JSON.

    Sorted keys, 2-space indent, trailing newline -- so committed baseline
    diffs stay minimal and `serialize_baseline(load_baseline(text)) == text`
    for any already-canonical document.
    """
    payload = {
        "baselineVersion": data.baseline_version,
        "entries": {
            file_path: dict(conventions) for file_path, conventions in data.entries.items()
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_baseline(diagnostics: Sequence[Diagnostic]) -> BaselineData:
    """Count `diagnostics` per `(file, convention)` to seed a new baseline.

    A diagnostic with no `convention_name` is counted under its
    `predicate_name` instead, so every diagnostic is captured.
    """
    entries: dict[str, dict[str, int]] = {}
    for diagnostic in diagnostics:
        file_counts = entries.setdefault(diagnostic.file_path, {})
        key = _convention_key(diagnostic)
        file_counts[key] = file_counts.get(key, 0) + 1

    return BaselineData(baseline_version=BASELINE_VERSION, entries=entries)


def apply_baseline(
    *,
    diagnostics: Sequence[Diagnostic],
    baseline: BaselineData,
) -> BaselineApplication:
    """Demote already-recorded diagnostics, leaving new violations to fail.

    Diagnostics are grouped by `(file_path, convention_key)` -- the same
    `convention_name`-or-`predicate_name` key `build_baseline` uses -- and,
    within each group, sorted by `(line, column, message)`. The first
    `recorded` diagnostics in that order are demoted into `baselined`;
    anything beyond that count stays in `remaining` (new violations).
    `remaining` otherwise preserves the input order of `diagnostics`.

    A group recorded in the baseline whose current diagnostic count is
    lower than the recorded count (including zero, when the group has no
    current diagnostics at all) produces a `BaselineStaleEntry`. The result
    is fully determined by its inputs.
    """
    groups: dict[tuple[str, str], list[Diagnostic]] = {}
    for diagnostic in diagnostics:
        groups.setdefault((diagnostic.file_path, _convention_key(diagnostic)), []).append(
            diagnostic
        )

    demoted_ids: set[int] = set()
    baselined: list[BaselinedDiagnostic] = []
    stale_entries: list[BaselineStaleEntry] = []
    seen_keys: set[tuple[str, str]] = set()

    for (file_path, convention_name), group in groups.items():
        seen_keys.add((file_path, convention_name))
        recorded = baseline.entries.get(file_path, {}).get(convention_name, 0)
        sorted_group = sorted(group, key=_diagnostic_sort_key)
        demote_count = min(recorded, len(sorted_group))

        for diagnostic in sorted_group[:demote_count]:
            demoted_ids.add(id(diagnostic))
            baselined.append(
                BaselinedDiagnostic(
                    diagnostic=diagnostic,
                    file_path=file_path,
                    convention_name=convention_name,
                )
            )

        if recorded > len(sorted_group):
            stale_entries.append(
                BaselineStaleEntry(
                    file_path=file_path,
                    convention_name=convention_name,
                    recorded_count=recorded,
                    found_count=len(sorted_group),
                )
            )

    for file_path, conventions in baseline.entries.items():
        for convention_name, recorded in conventions.items():
            if (file_path, convention_name) in seen_keys:
                continue
            stale_entries.append(
                BaselineStaleEntry(
                    file_path=file_path,
                    convention_name=convention_name,
                    recorded_count=recorded,
                    found_count=0,
                )
            )

    remaining = [diagnostic for diagnostic in diagnostics if id(diagnostic) not in demoted_ids]
    stale_entries.sort(key=lambda entry: (entry.file_path, entry.convention_name))

    return BaselineApplication(
        remaining=remaining,
        baselined=baselined,
        stale_entries=stale_entries,
    )


def _convention_key(diagnostic: Diagnostic) -> str:
    return diagnostic.convention_name or diagnostic.predicate_name


def _diagnostic_sort_key(diagnostic: Diagnostic) -> tuple[int, int, str]:
    line = diagnostic.line if diagnostic.line is not None else -1
    column = diagnostic.column if diagnostic.column is not None else -1
    return (line, column, diagnostic.message)


__all__ = [
    "BASELINE_VERSION",
    "BaselineApplication",
    "BaselineData",
    "BaselineStaleEntry",
    "BaselinedDiagnostic",
    "apply_baseline",
    "build_baseline",
    "load_baseline",
    "serialize_baseline",
]
