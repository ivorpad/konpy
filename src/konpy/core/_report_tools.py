"""External-tool lanes for the zero-config report.

Runs ruff, basedpyright, and import-linter as independent subprocesses and
translates each into a `ReportToolLane`. A missing binary, a missing config,
a timeout, or output konpy can't parse all degrade to a status line instead
of raising: an external tool never fails the report or changes its exit code.
"""

from __future__ import annotations

import configparser
import json
import re
import subprocess
import tomllib
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from konpy.core._report_tool_support import (
    Runner,
    more_items_note,
    resolve_tool_executable,
    run_tool,
)

ReportToolStatus = Literal["ok", "not-installed", "no-config", "timed-out", "error"]

_TOP_ITEMS = 5
_MESSAGE_TRUNCATE = 60
_EXTRAS_HINT = 'pip install "konpy[quality]"'
_IMPORT_BOUNDARIES_HINT = "no contracts configured -- see docs/guides/import-boundaries.md"

# Single source of truth for how each non-"ok" status reads in the report;
# shared with `_report_render` so the two never drift on wording.
STATUS_LABEL: dict[ReportToolStatus, str] = {
    "ok": "ok",
    "not-installed": "not installed",
    "no-config": "no config",
    "timed-out": "timed out",
    "error": "error",
}

_CONTRACTS_SUMMARY_RE = re.compile(r"Contracts:\s*(\d+)\s*kept,\s*(\d+)\s*broken", re.IGNORECASE)
_BROKEN_CONTRACT_RE = re.compile(r"^(.*\S)\s+BROKEN\s*$", re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class ReportToolLane:
    """One external tool's contribution to the zero-config report."""

    name: str
    status: ReportToolStatus
    findings: int
    top_items: tuple[str, ...]
    note: str | None
    duration_ms: float


def _elapsed(start: float) -> float:
    return (perf_counter() - start) * 1000


def _truncate(text: str, limit: int = _MESSAGE_TRUNCATE) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _not_installed(name: str, start: float) -> ReportToolLane:
    return ReportToolLane(
        name=name,
        status="not-installed",
        findings=0,
        top_items=(),
        note=_EXTRAS_HINT,
        duration_ms=_elapsed(start),
    )


def _timed_out(name: str, start: float, timeout: float) -> ReportToolLane:
    return ReportToolLane(
        name=name,
        status="timed-out",
        findings=0,
        top_items=(),
        note=f"exceeded {timeout:g}s",
        duration_ms=_elapsed(start),
    )


def _error(name: str, start: float, stderr: str) -> ReportToolLane:
    return ReportToolLane(
        name=name,
        status="error",
        findings=0,
        top_items=(),
        note=_first_line(stderr) or "could not run",
        duration_ms=_elapsed(start),
    )


def _ruff_lane(root: Path, *, timeout: float, runner: Runner) -> ReportToolLane:
    name = "ruff"
    start = perf_counter()
    try:
        completed = run_tool(
            [resolve_tool_executable(root, "ruff"), "check", "--output-format", "json"],
            root=root,
            timeout=timeout,
            runner=runner,
        )
    except FileNotFoundError:
        return _not_installed(name, start)
    except subprocess.TimeoutExpired:
        return _timed_out(name, start, timeout)

    if completed.returncode not in (0, 1):
        return _error(name, start, completed.stderr)
    try:
        raw_findings = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _error(name, start, completed.stderr or "could not parse ruff output")

    counts: Counter[str] = Counter()
    first_message: dict[str, str] = {}
    for item in raw_findings:
        code = item.get("code") or "other"
        counts[code] += 1
        first_message.setdefault(code, item.get("message", ""))

    ranked = counts.most_common(_TOP_ITEMS)
    top_items = tuple(
        f"{code} x{count}  {_truncate(first_message.get(code, ''))}".rstrip()
        for code, count in ranked
    ) + more_items_note(sum(count for _, count in ranked), len(raw_findings))
    return ReportToolLane(
        name=name,
        status="ok",
        findings=len(raw_findings),
        top_items=top_items,
        note=None,
        duration_ms=_elapsed(start),
    )


def _basedpyright_lane(root: Path, *, timeout: float, runner: Runner) -> ReportToolLane:
    name = "basedpyright"
    start = perf_counter()
    try:
        completed = run_tool(
            [resolve_tool_executable(root, "basedpyright"), "--outputjson"],
            root=root,
            timeout=timeout,
            runner=runner,
        )
    except FileNotFoundError:
        return _not_installed(name, start)
    except subprocess.TimeoutExpired:
        return _timed_out(name, start, timeout)

    if completed.returncode not in (0, 1):
        return _error(name, start, completed.stderr)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _error(name, start, completed.stderr or "could not parse basedpyright output")

    summary = payload.get("summary", {})
    findings = int(summary.get("errorCount", 0)) + int(summary.get("warningCount", 0))
    counts = Counter(
        diagnostic.get("rule") or "other" for diagnostic in payload.get("generalDiagnostics", [])
    )
    ranked = counts.most_common(_TOP_ITEMS)
    top_items = tuple(f"{rule} x{count}" for rule, count in ranked) + more_items_note(
        sum(count for _, count in ranked), sum(counts.values())
    )
    return ReportToolLane(
        name=name,
        status="ok",
        findings=findings,
        top_items=top_items,
        note=None,
        duration_ms=_elapsed(start),
    )


def _has_import_linter_config(root: Path) -> bool:
    """Check whether import-linter contracts are configured under `root`."""
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            data = {}
        if "importlinter" in data.get("tool", {}):
            return True

    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(setup_cfg, encoding="utf-8")
        except configparser.Error:
            pass
        else:
            if parser.has_section("importlinter"):
                return True

    return (root / ".importlinter").is_file()


def _import_linter_lane(root: Path, *, timeout: float, runner: Runner) -> ReportToolLane:
    name = "import-linter"
    start = perf_counter()
    if not _has_import_linter_config(root):
        return ReportToolLane(
            name=name,
            status="no-config",
            findings=0,
            top_items=(),
            note=_IMPORT_BOUNDARIES_HINT,
            duration_ms=_elapsed(start),
        )

    try:
        completed = run_tool(
            [resolve_tool_executable(root, "lint-imports")],
            root=root,
            timeout=timeout,
            runner=runner,
        )
    except FileNotFoundError:
        return _not_installed(name, start)
    except subprocess.TimeoutExpired:
        return _timed_out(name, start, timeout)

    match = _CONTRACTS_SUMMARY_RE.search(completed.stdout)
    if match is None:
        return _error(name, start, completed.stderr or "could not parse import-linter output")

    kept, broken = int(match.group(1)), int(match.group(2))
    broken_contracts = tuple(_BROKEN_CONTRACT_RE.findall(completed.stdout))[:_TOP_ITEMS]
    return ReportToolLane(
        name=name,
        status="ok",
        findings=broken,
        top_items=broken_contracts + more_items_note(len(broken_contracts), broken),
        note=f"{kept} kept",
        duration_ms=_elapsed(start),
    )


def collect_tool_lanes(
    root: Path,
    *,
    timeout: float = 60.0,
    runner: Runner = subprocess.run,
) -> tuple[ReportToolLane, ...]:
    """Run ruff, basedpyright, and import-linter concurrently and summarize each.

    Each tool runs in its own thread over an independent subprocess, so
    wall-clock cost is the slowest tool, not their sum. Every lane degrades to
    a status line on failure -- a missing binary, an unconfigured tool, a
    timeout, or unparsable output never raises out of this function and never
    changes the report's exit code.
    """
    jobs: tuple[Callable[[], ReportToolLane], ...] = (
        lambda: _ruff_lane(root, timeout=timeout, runner=runner),
        lambda: _basedpyright_lane(root, timeout=timeout, runner=runner),
        lambda: _import_linter_lane(root, timeout=timeout, runner=runner),
    )
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(job) for job in jobs]
        return tuple(future.result() for future in futures)


__all__ = [
    "STATUS_LABEL",
    "ReportToolLane",
    "ReportToolStatus",
    "collect_tool_lanes",
]
