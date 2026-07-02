"""Lightweight A/B proof harness for konsistent.

Runs `konsistent check --format json` against a target repository and reduces
the output into a stable, diffable metrics summary, so two agent runs (e.g.
"with `konsistent explain` guidance injected + hook enforcement" vs "without")
can be compared quantitatively. This is stdlib-only and shells out to the
`konsistent` CLI (or `python -m konsistent`) as a subprocess; it does not
import the `konsistent` package.

It is a repo-dev script, not part of the installable `konsistent` package —
it lives beside `scripts/generate_schema.py` and is tested the same way (see
`tests/unit/test_eval_conventions.py`).

Usage:

    uv run python scripts/eval_conventions.py run <target-repo> [options]
    uv run python scripts/eval_conventions.py compare <before.json> <after.json> [options]

Run from the repo root: `uv run python scripts/eval_conventions.py run .`

Note on truncation: konsistent's own `--format json` truncates both the
`diagnostics` array and the `summary.errors`/`summary.warnings` counts to
`--max-diagnostics` (default 100 in konsistent itself) before rendering. This
script always passes an explicit, much higher `--max-diagnostics` (default
1,000,000, see DEFAULT_MAX_DIAGNOSTICS) so metrics are not silently
undercounted. If you override `--max-diagnostics` to a low value here, or
duplicate `--max-diagnostics` via `--extra-arg`, counts will be truncated
again.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_TOP_FILES = 10
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_DIAGNOSTICS = (
    1_000_000  # override konsistent's low default (100) so counts aren't truncated
)
STDOUT_SNIPPET_LIMIT = 2000  # chars of stdout/stderr included in EvalError messages

UNUSED_CONVENTION_NAME = "unused-code"
UNUSED_DEAD_PREDICATE = "unusedCode.dead"
UNUSED_TEST_ONLY_PREDICATE = "unusedCode.testOnly"
NO_CONVENTION_KEY = "(none)"
UNKNOWN_PREDICATE_KEY = "(unknown)"

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_HARNESS_ERROR = 2

_SUMMARY_ROW_ORDER = (
    ("filesChecked", "files checked"),
    ("totalDiagnostics", "total diagnostics"),
    ("errors", "errors"),
    ("warnings", "warnings"),
    ("suppressed", "suppressed"),
)


class EvalError(RuntimeError):
    """Harness-level failure: bad target path, unparseable konsistent output,
    subprocess launch failure, or timeout. Never raised for a target repo
    simply having lint violations -- that is the normal/expected case."""


@dataclasses.dataclass(frozen=True)
class RunOutcome:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    wall_clock_ms: float


# Injectable for tests: same call shape as run_konsistent_check.
CheckRunner = Callable[[list[str], Path, float], RunOutcome]


def resolve_konsistent_argv(*, konsistent_bin: str | None) -> list[str]:
    """Return the base argv prefix used to invoke konsistent (before subcommand args).

    Order:
    1. konsistent_bin is not None -> [konsistent_bin]  (used verbatim, no splitting)
    2. shutil.which("konsistent") returns a path -> [that path]
    3. fallback -> [sys.executable, "-m", "konsistent"]
    """
    if konsistent_bin is not None:
        return [konsistent_bin]

    found = shutil.which("konsistent")
    if found is not None:
        return [found]

    return [sys.executable, "-m", "konsistent"]


def build_check_argv(
    *,
    base_argv: list[str],
    config_path: str | None,
    diagnostic_level: str | None,
    placeholders: Sequence[str],
    max_diagnostics: int,
    extra_args: Sequence[str],
) -> list[str]:
    """Assemble the full argv for `konsistent check --format json ...`."""
    argv = [*base_argv, "check", "--format", "json", "--max-diagnostics", str(max_diagnostics)]

    if config_path:
        argv.extend(["--config-path", config_path])
    if diagnostic_level:
        argv.extend(["--diagnostic-level", diagnostic_level])
    for placeholder in placeholders:
        argv.extend(["--placeholder", placeholder])
    argv.extend(extra_args)

    return argv


def run_konsistent_check(argv: list[str], cwd: Path, timeout_seconds: float) -> RunOutcome:
    """Run konsistent as a subprocess and capture its output."""
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = (time.monotonic() - started) * 1000
        return RunOutcome(
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            timed_out=True,
            wall_clock_ms=elapsed,
        )
    except OSError as exc:
        raise EvalError(f"failed to launch konsistent ({argv[0]!r}): {exc}") from exc

    elapsed = (time.monotonic() - started) * 1000
    return RunOutcome(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        wall_clock_ms=elapsed,
    )


def parse_check_json(*, stdout: str) -> dict[str, Any]:
    """Parse konsistent's --format json stdout into a dict, defensively."""
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        snippet = stdout[:STDOUT_SNIPPET_LIMIT]
        raise EvalError(
            f"could not parse konsistent output as JSON: {exc} (stdout={snippet!r})"
        ) from exc

    if not isinstance(parsed, dict):
        raise EvalError(
            f"expected konsistent output to be a JSON object, got {type(parsed).__name__}"
        )

    missing = [key for key in ("diagnostics", "summary") if key not in parsed]
    if missing:
        present = sorted(parsed.keys())
        raise EvalError(
            f"konsistent output missing required key(s) {missing}; keys present: {present}"
        )

    return parsed


def summarize(*, raw: dict[str, Any], top_files: int = DEFAULT_TOP_FILES) -> dict[str, Any]:
    """Reduce konsistent's parsed --format json payload into the metrics shape."""
    diagnostics = raw.get("diagnostics") or []
    raw_summary = raw.get("summary") or {}

    severity_counter: Counter[str] = Counter()
    convention_counter: Counter[str] = Counter()
    predicate_counter: Counter[str] = Counter()
    file_counter: Counter[str] = Counter()
    unused_dead = 0
    unused_test_only = 0

    for diag in diagnostics:
        severity = diag.get("severity") or "error"
        convention_name = diag.get("conventionName") or NO_CONVENTION_KEY
        predicate_name = diag.get("predicateName") or UNKNOWN_PREDICATE_KEY
        file_path = diag.get("filePath") or ""

        severity_counter[severity] += 1
        convention_counter[convention_name] += 1
        predicate_counter[predicate_name] += 1
        if file_path:
            file_counter[file_path] += 1

        if predicate_name == UNUSED_DEAD_PREDICATE:
            unused_dead += 1
        elif predicate_name == UNUSED_TEST_ONLY_PREDICATE:
            unused_test_only += 1

    top_files_list = [
        {"filePath": file_path, "count": count}
        for file_path, count in sorted(file_counter.items(), key=lambda item: (-item[1], item[0]))[
            :top_files
        ]
    ]

    return {
        "summary": {
            "filesChecked": raw_summary.get("filesChecked", 0),
            "totalDiagnostics": len(diagnostics),
            "errors": raw_summary.get("errors", 0),
            "warnings": raw_summary.get("warnings", 0),
            "suppressed": raw_summary.get("suppressed", 0),
            "konsistentDurationMs": raw_summary.get("durationMs"),
        },
        "bySeverity": dict(sorted(severity_counter.items())),
        "byConvention": dict(sorted(convention_counter.items())),
        "byPredicate": dict(sorted(predicate_counter.items())),
        "unusedCode": {
            "dead": unused_dead,
            "testOnly": unused_test_only,
            "total": unused_dead + unused_test_only,
        },
        "topFiles": top_files_list,
    }


def build_metrics(
    *,
    target_repo: Path,
    config_path: str | None,
    konsistent_bin: str | None,
    diagnostic_level: str | None,
    placeholders: Sequence[str],
    max_diagnostics: int,
    extra_args: Sequence[str],
    label: str | None,
    top_files: int,
    timeout_seconds: float,
    runner: CheckRunner | None = None,
) -> dict[str, Any]:
    """Top-level orchestration for the `run` command."""
    target_repo = target_repo.resolve()
    if not target_repo.is_dir():
        raise EvalError(f"target repo not found or not a directory: {target_repo}")

    base_argv = resolve_konsistent_argv(konsistent_bin=konsistent_bin)
    argv = build_check_argv(
        base_argv=base_argv,
        config_path=config_path,
        diagnostic_level=diagnostic_level,
        placeholders=placeholders,
        max_diagnostics=max_diagnostics,
        extra_args=extra_args,
    )

    active_runner = runner or run_konsistent_check
    outcome = active_runner(argv, target_repo, timeout_seconds)

    if outcome.timed_out:
        raise EvalError(f"konsistent check timed out after {timeout_seconds}s (argv={argv!r})")

    try:
        raw = parse_check_json(stdout=outcome.stdout)
    except EvalError as exc:
        stderr_snippet = outcome.stderr[:STDOUT_SNIPPET_LIMIT]
        raise EvalError(
            f"{exc} (exit_code={outcome.exit_code}, stderr={stderr_snippet!r})"
        ) from exc

    summary = summarize(raw=raw, top_files=top_files)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "meta": {
            "label": label,
            "targetRepo": str(target_repo),
            "command": argv,
            "exitCode": outcome.exit_code,
            "durationMsWallClock": outcome.wall_clock_ms,
            "generatedAt": datetime.now(UTC).isoformat(),
            "configPath": config_path,
        },
        **summary,
    }


def _delta_scalar(before: float | None, after: float | None) -> float:
    """Coerce None to 0.0 for delta computation only (raw values passed through elsewhere)."""
    return (after or 0.0) - (before or 0.0)


def _diff_counter(before: dict[str, int], after: dict[str, int]) -> dict[str, dict[str, int]]:
    """Union of before/after keys (sorted alphabetically), each -> before/after/delta."""
    keys = sorted(set(before) | set(after))
    return {
        key: {
            "before": before.get(key, 0),
            "after": after.get(key, 0),
            "delta": after.get(key, 0) - before.get(key, 0),
        }
        for key in keys
    }


def detect_regression(*, before_errors: int, after_errors: int) -> bool:
    """True iff after_errors > before_errors (strict increase in error-severity count)."""
    return after_errors > before_errors


def compare_summaries(*, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Diff two build_metrics()-shaped dicts."""
    for side_name, side in (("before", before), ("after", after)):
        version = side.get("schemaVersion")
        if version != SCHEMA_VERSION:
            raise EvalError(
                f"{side_name} summary has schemaVersion={version!r}, expected {SCHEMA_VERSION}"
            )

    before_summary = before["summary"]
    after_summary = after["summary"]

    summary_diff: dict[str, dict[str, Any]] = {}
    for key in ("filesChecked", "totalDiagnostics", "errors", "warnings", "suppressed"):
        before_value = before_summary.get(key, 0)
        after_value = after_summary.get(key, 0)
        summary_diff[key] = {
            "before": before_value,
            "after": after_value,
            "delta": after_value - before_value,
        }

    duration_before = before_summary.get("konsistentDurationMs")
    duration_after = after_summary.get("konsistentDurationMs")
    summary_diff["konsistentDurationMs"] = {
        "before": duration_before,
        "after": duration_after,
        "delta": _delta_scalar(duration_before, duration_after),
    }

    before_unused = before["unusedCode"]
    after_unused = after["unusedCode"]
    unused_diff = {
        key: {
            "before": before_unused[key],
            "after": after_unused[key],
            "delta": after_unused[key] - before_unused[key],
        }
        for key in ("dead", "testOnly", "total")
    }

    regression = detect_regression(
        before_errors=summary_diff["errors"]["before"],
        after_errors=summary_diff["errors"]["after"],
    )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "beforeLabel": before["meta"].get("label"),
        "afterLabel": after["meta"].get("label"),
        "beforeMeta": before["meta"],
        "afterMeta": after["meta"],
        "summary": summary_diff,
        "bySeverity": _diff_counter(before["bySeverity"], after["bySeverity"]),
        "byConvention": _diff_counter(before["byConvention"], after["byConvention"]),
        "byPredicate": _diff_counter(before["byPredicate"], after["byPredicate"]),
        "unusedCode": unused_diff,
        "regression": regression,
    }


def _format_row(
    label: str, before: int, after: int, delta: int, *, name_width: int, value_width: int
) -> str:
    return (
        f"  {label:<{name_width}} {before:>{value_width}} -> {after:>{value_width}}  ({delta:+d})"
    )


def _format_named_diff_section(title: str, diff: dict[str, dict[str, int]]) -> list[str]:
    lines = ["", f"{title}:"]
    rows = [
        (name, entry)
        for name, entry in sorted(diff.items())
        if entry["before"] != 0 or entry["after"] != 0
    ]
    if not rows:
        lines.append("  (no differences)")
        return lines

    for name, entry in rows:
        lines.append(
            _format_row(
                name, entry["before"], entry["after"], entry["delta"], name_width=30, value_width=4
            )
        )
    return lines


def format_compare_table(*, comparison: dict[str, Any]) -> str:
    """Human-readable fixed-width text report."""
    before_label = comparison["beforeLabel"] or "before"
    after_label = comparison["afterLabel"] or "after"

    lines = [f"konsistent eval comparison: {before_label} vs {after_label}", ""]

    for key, human_label in _SUMMARY_ROW_ORDER:
        entry = comparison["summary"][key]
        lines.append(
            _format_row(
                human_label,
                entry["before"],
                entry["after"],
                entry["delta"],
                name_width=18,
                value_width=6,
            )
        )

    lines.extend(_format_named_diff_section("By convention", comparison["byConvention"]))
    lines.extend(_format_named_diff_section("By predicate", comparison["byPredicate"]))

    unused = comparison["unusedCode"]
    lines.append("")
    lines.append("Unused code:")
    for key, human_label in (("dead", "dead"), ("testOnly", "test-only"), ("total", "total")):
        entry = unused[key]
        lines.append(
            _format_row(
                human_label,
                entry["before"],
                entry["after"],
                entry["delta"],
                name_width=30,
                value_width=4,
            )
        )

    lines.append("")
    regression_text = "FAIL - errors increased" if comparison["regression"] else "PASS"
    lines.append(f"Regression check: {regression_text}")

    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval_conventions.py",
        description=(
            "Run `konsistent check --format json` against a target repository and "
            "reduce the output into a stable, diffable metrics summary."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run konsistent check against a target repo.")
    run_parser.add_argument("target_repo", type=Path, help="Path to the repo to check.")
    run_parser.add_argument("--config-path", type=str, default=None)
    run_parser.add_argument("--konsistent-bin", type=str, default=None)
    run_parser.add_argument(
        "--diagnostic-level", type=str, default=None, choices=["warning", "error"]
    )
    run_parser.add_argument(
        "--placeholder",
        action="append",
        default=[],
        help="Repeatable NAME:VALUE placeholder to forward to konsistent.",
    )
    run_parser.add_argument("--max-diagnostics", type=int, default=DEFAULT_MAX_DIAGNOSTICS)
    run_parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Repeatable extra argv token forwarded verbatim to konsistent check.",
    )
    run_parser.add_argument("--label", type=str, default=None)
    run_parser.add_argument("--output", type=Path, default=None)
    run_parser.add_argument("--top-files", type=int, default=DEFAULT_TOP_FILES)
    run_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    run_parser.add_argument("--indent", type=int, default=2)

    compare_parser = subparsers.add_parser(
        "compare", help="Diff two metrics-summary JSON files produced by `run`."
    )
    compare_parser.add_argument("before", type=Path)
    compare_parser.add_argument("after", type=Path)
    compare_parser.add_argument("--format", type=str, default="table", choices=["table", "json"])
    compare_parser.add_argument("--output", type=Path, default=None)
    compare_parser.add_argument("--fail-on-regression", action="store_true", default=False)
    compare_parser.add_argument("--indent", type=int, default=2)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    try:
        metrics = build_metrics(
            target_repo=Path(args.target_repo),
            config_path=args.config_path,
            konsistent_bin=args.konsistent_bin,
            diagnostic_level=args.diagnostic_level,
            placeholders=args.placeholder,
            max_diagnostics=args.max_diagnostics,
            extra_args=args.extra_arg,
            label=args.label,
            top_files=args.top_files,
            timeout_seconds=args.timeout,
            runner=None,
        )
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_HARNESS_ERROR

    text = json.dumps(metrics, indent=args.indent)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    return EXIT_OK


def _load_summary_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise EvalError(f"summary file not found: {path}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvalError(f"could not parse summary file as JSON: {path}: {exc}") from exc


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        before = _load_summary_file(Path(args.before))
        after = _load_summary_file(Path(args.after))
        comparison = compare_summaries(before=before, after=after)
    except EvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_HARNESS_ERROR

    if args.format == "json":
        text = json.dumps(comparison, indent=args.indent)
    else:
        text = format_compare_table(comparison=comparison)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    if args.fail_on_regression and comparison["regression"]:
        return EXIT_REGRESSION

    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "compare":
        return cmd_compare(args)

    parser.print_usage(sys.stderr)
    return EXIT_HARNESS_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
