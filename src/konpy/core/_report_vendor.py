"""Vendor and template tree detection for the zero-config report.

Real multi-service repos carry trees that are not the codebase under review:
cookiecutter scaffolds (dir segments like `{{ cookiecutter.project_slug }}`,
or any tree rooted at a directory holding a `cookiecutter.json`), vendored
snapshots (`vendor/`, `third_party/`, `downloads/`, `pkg@<revision>` copies),
and gitignored build junk. Left alone these dominate file counts, unused-code
findings, and coverage percentages. `detect_vendor_paths` classifies which of
a candidate file list falls into each bucket so the report can drop them from
its own accounting while still feeding them to the unused-code engine as
reference-only sources -- the same "skip but don't mask" pattern
`_report_generated.py` uses for generator output.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_TEMPLATE_OPEN = "{{"
_TEMPLATE_CLOSE = "}}"
_COOKIECUTTER_MANIFEST = "cookiecutter.json"

_VENDORED_DIR_NAMES = frozenset(
    {"downloads", "vendor", "vendors", "third_party", "thirdparty", "_vendor"}
)
# Snapshot dirs (`libs-x@a1b2c3d`): the part after `@` must look like a
# revision, not a branch/tag name (`pkg@main` is not a snapshot).
_MIN_REVISION_HEX_LENGTH = 7
_HEX_DIGITS = frozenset("0123456789abcdef")

_GIT_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, kw_only=True)
class VendorClassification:
    """Files classified as template, vendored, or gitignored, plus matched roots.

    The three sets are disjoint: a file matching more than one rule is
    counted once, by precedence template > vendored > gitignored.
    `matched_roots` are the template/vendored directory roots that triggered
    a match (gitignored files are not necessarily a "tree", so they don't
    contribute roots), for the report header's note.
    """

    template_files: frozenset[str]
    vendored_files: frozenset[str]
    gitignored_files: frozenset[str]
    matched_roots: tuple[str, ...]


def detect_vendor_paths(root: Path, files: Sequence[str]) -> VendorClassification:
    """Classify `files` (POSIX-relative paths under `root`) by vendor/template/gitignore rules.

    - template: a path segment containing both `{{` and `}}`, or any file
      under a directory that directly holds a `cookiecutter.json`.
    - vendored: a path segment named `downloads`, `vendor`, `vendors`,
      `third_party`, `thirdparty`, or `_vendor`, or a `name@revision`
      snapshot-dir segment (revision >=7 hex-ish characters).
    - gitignored: files `git ls-files --others --ignored --exclude-standard`
      reports, when `root` is a git worktree (empty set otherwise).
    """
    cookiecutter_dirs = _cookiecutter_directories(root, files)
    template: set[str] = set()
    vendored: set[str] = set()
    roots: set[str] = set()

    for path in files:
        dir_segments = path.split("/")[:-1]

        template_root = _template_root(dir_segments, cookiecutter_dirs)
        if template_root is not None:
            template.add(path)
            roots.add(template_root)
            continue

        vendored_root = _vendored_root(dir_segments)
        if vendored_root is not None:
            vendored.add(path)
            roots.add(vendored_root)

    gitignored = (_gitignored_files(root) & set(files)) - template - vendored

    return VendorClassification(
        template_files=frozenset(template),
        vendored_files=frozenset(vendored),
        gitignored_files=frozenset(gitignored),
        matched_roots=tuple(sorted(roots)),
    )


def _cookiecutter_directories(root: Path, files: Sequence[str]) -> frozenset[str]:
    """Directories (relative to `root`, among `files`' ancestors) directly holding a manifest."""
    candidates: set[str] = {""}
    for path in files:
        segments = path.split("/")[:-1]
        for i in range(len(segments) + 1):
            candidates.add("/".join(segments[:i]))
    return frozenset(
        candidate
        for candidate in candidates
        if (root / candidate / _COOKIECUTTER_MANIFEST).is_file()
    )


def _template_root(dir_segments: Sequence[str], cookiecutter_dirs: frozenset[str]) -> str | None:
    for i, segment in enumerate(dir_segments):
        if _TEMPLATE_OPEN in segment and _TEMPLATE_CLOSE in segment:
            return "/".join(dir_segments[: i + 1]) + "/"
    for i in range(len(dir_segments) + 1):
        candidate = "/".join(dir_segments[:i])
        if candidate in cookiecutter_dirs:
            return f"{candidate}/" if candidate else "./"
    return None


def _vendored_root(dir_segments: Sequence[str]) -> str | None:
    for i, segment in enumerate(dir_segments):
        if segment in _VENDORED_DIR_NAMES or _is_snapshot_segment(segment):
            return "/".join(dir_segments[: i + 1]) + "/"
    return None


def _is_snapshot_segment(segment: str) -> bool:
    name, separator, revision = segment.rpartition("@")
    if not separator or not name or len(revision) < _MIN_REVISION_HEX_LENGTH:
        return False
    return all(char in _HEX_DIGITS for char in revision.lower())


def _gitignored_files(root: Path) -> frozenset[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--ignored", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    return frozenset(line.strip() for line in result.stdout.splitlines() if line.strip())


__all__ = ["VendorClassification", "detect_vendor_paths"]
