"""E2E: `scripts/eval_conventions.py run <fixture>` against real fixture repos.

Unlike the other `tests/e2e/test_*.py` modules, this does not go through the
in-process `run_cli` fixture (that drives the `konpy` Typer app
directly). `scripts/eval_conventions.py` is a standalone script that itself
shells out to the built `konpy` CLI as a subprocess, so exercising it
"end to end" means invoking the script as a real subprocess too -- covering
the full path: script subprocess -> konpy subprocess -> JSON parsing ->
metrics summary.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_conventions.py"


def _run_eval(fixture: Path, *extra_args: str) -> tuple[int, dict, str]:
    completed = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT), "run", str(fixture), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )
    metrics = json.loads(completed.stdout)
    return completed.returncode, metrics, completed.stderr


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestEvalConventionsCleanFixture:
    def test_run_reports_zero_diagnostics(self, fixtures_dir: Path) -> None:
        exit_code, metrics, stderr = _run_eval(_fixture(fixtures_dir, "eval-conventions-clean"))

        assert exit_code == 0
        assert stderr == ""
        assert metrics["summary"]["filesChecked"] == 1
        assert metrics["summary"]["totalDiagnostics"] == 0
        assert metrics["summary"]["errors"] == 0
        assert metrics["byConvention"] == {}
        assert metrics["meta"]["exitCode"] == 0


class TestEvalConventionsBrokenFixture:
    def test_run_reports_the_missing_export_violation(self, fixtures_dir: Path) -> None:
        exit_code, metrics, stderr = _run_eval(_fixture(fixtures_dir, "eval-conventions-broken"))

        # The harness's own exit code reflects the harness (0 = ran cleanly),
        # not the target repo's violations -- those are recorded
        # informationally in meta.exitCode. See scripts/eval_conventions.py
        # EXIT_* contract and docs/guides/agent-eval.md.
        assert exit_code == 0
        assert stderr == ""
        assert metrics["meta"]["exitCode"] == 1
        assert metrics["summary"]["filesChecked"] == 1
        assert metrics["summary"]["totalDiagnostics"] == 1
        assert metrics["summary"]["errors"] == 1
        assert metrics["byConvention"] == {"service-exports-run": 1}
        assert metrics["byPredicate"] == {"export": 1}
        assert metrics["topFiles"] == [{"filePath": "src/service.py", "count": 1}]

    def test_compare_between_clean_and_broken_detects_a_regression(
        self, fixtures_dir: Path, tmp_path: Path
    ) -> None:
        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"

        before_code, before_metrics, _ = _run_eval(
            _fixture(fixtures_dir, "eval-conventions-clean"), "--label", "before"
        )
        after_code, after_metrics, _ = _run_eval(
            _fixture(fixtures_dir, "eval-conventions-broken"), "--label", "after"
        )
        assert before_code == 0
        assert after_code == 0
        before_path.write_text(json.dumps(before_metrics), encoding="utf-8")
        after_path.write_text(json.dumps(after_metrics), encoding="utf-8")

        compare = subprocess.run(
            [
                sys.executable,
                str(EVAL_SCRIPT),
                "compare",
                str(before_path),
                str(after_path),
                "--format",
                "json",
                "--fail-on-regression",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert compare.returncode == 1
        comparison = json.loads(compare.stdout)
        assert comparison["regression"] is True
        assert comparison["summary"]["errors"] == {"before": 0, "after": 1, "delta": 1}
