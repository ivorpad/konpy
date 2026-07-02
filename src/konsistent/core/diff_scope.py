"""Resolve `--files`/`--changed` CLI input into a `run()` target-file scope.

`resolve_diff_scope` is the single entry point: it returns `Ok(None)` when
neither flag is given (no scoping — current, default behavior), or
`Ok(frozenset[str])` — a normalized, possibly empty set of project-relative
paths — when either flag is given. See `docs/reference/cli.md` for the full
scoping semantics (path-intersection rules, `havePairedFile`/`unusedCode`
caveats).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from konsistent.config.errors import Err, Ok, Result
from konsistent.core.filesystem import normalize_relative_path


def resolve_diff_scope(
    *,
    files: Sequence[str] | None,
    changed: bool,
    cwd: Path,
) -> Result[frozenset[str] | None]:
    """Resolve `--files`/`--changed` CLI input into a target-file scope.

    Returns `Ok(None)` when neither flag is given (no scoping — the default).
    Returns `Ok(frozenset[str])` — normalized, project-relative-when-possible,
    forward-slash paths, possibly empty — when either flag is given.
    Returns `Err` when both flags are given, or `--changed` fails to invoke git.
    """
    has_files = bool(files)
    if has_files and changed:
        return Err("Cannot combine --files and --changed; choose one.")

    if not has_files and not changed:
        return Ok(None)

    if changed:
        changed_result = compute_changed_files(cwd=cwd)
        if isinstance(changed_result, Err):
            return changed_result
        raw_paths: Sequence[str] = changed_result.value
    else:
        raw_paths = files or []

    normalized = frozenset(
        normalize_relative_path(_to_repo_relative(path, cwd=cwd))
        for path in raw_paths
        if path.strip()
    )
    return Ok(normalized)


def compute_changed_files(*, cwd: Path) -> Result[list[str]]:
    """Tracked changes (`git diff --name-only HEAD`) followed by untracked
    files (`git ls-files --others --exclude-standard`), deduplicated
    (first occurrence wins, diff-tracked entries take priority in ordering).
    Paths are relative to `cwd` (git's own relative-to-invocation-directory
    behavior for `ls-files`; `--relative` is passed to `diff` for parity).
    """
    work_tree_check = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if isinstance(work_tree_check, Err):
        return Err(f"--changed requires a git repository (none found at {cwd}).")

    diff_result = _run_git(["diff", "--name-only", "--relative", "HEAD"], cwd=cwd)
    if isinstance(diff_result, Err):
        return diff_result

    untracked_result = _run_git(["ls-files", "--others", "--exclude-standard"], cwd=cwd)
    if isinstance(untracked_result, Err):
        return untracked_result

    seen: set[str] = set()
    ordered: list[str] = []
    for raw in (*diff_result.value, *untracked_result.value):
        normalized = raw.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)

    return Ok(ordered)


def _run_git(args: list[str], *, cwd: Path) -> Result[list[str]]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return Err(f"Failed to run git {' '.join(args)}: {error}")

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        return Err(f"git {' '.join(args)} failed (exit {completed.returncode}): {stderr}")

    return Ok(completed.stdout.splitlines())


def _to_repo_relative(path: str, *, cwd: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(cwd))
        except ValueError:
            return str(candidate)  # outside cwd: left as-is, will simply match nothing
    return path


__all__ = ["compute_changed_files", "resolve_diff_scope"]
