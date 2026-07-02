import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import eval_conventions  # noqa: E402
from eval_conventions import (  # noqa: E402
    EvalError,
    RunOutcome,
    build_arg_parser,
    build_check_argv,
    build_metrics,
    compare_summaries,
    detect_regression,
    format_compare_table,
    main,
    parse_check_json,
    resolve_konsistent_argv,
    run_konsistent_check,
    summarize,
)


def _fake_runner(outcome: RunOutcome) -> Callable[[list[str], Path, float], RunOutcome]:
    calls: list[tuple[list[str], Path, float]] = []

    def runner(argv: list[str], cwd: Path, timeout_seconds: float) -> RunOutcome:
        calls.append((argv, cwd, timeout_seconds))
        return outcome

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def _outcome(**overrides: object) -> RunOutcome:
    defaults: dict[str, object] = {
        "exit_code": 0,
        "stdout": '{"diagnostics": [], "suppressed": [], "summary": '
        '{"filesChecked": 0, "errors": 0, "warnings": 0, "suppressed": 0, "durationMs": 1.0}}',
        "stderr": "",
        "timed_out": False,
        "wall_clock_ms": 12.5,
    }
    defaults.update(overrides)
    return RunOutcome(**defaults)  # type: ignore[arg-type]


class TestResolveKonsistentArgv:
    def test_resolve_konsistent_argv_prefers_explicit_bin(self) -> None:
        assert resolve_konsistent_argv(konsistent_bin="/x/konsistent") == ["/x/konsistent"]

    def test_resolve_konsistent_argv_uses_path_lookup(self, monkeypatch) -> None:
        monkeypatch.setattr(eval_conventions.shutil, "which", lambda _name: "/usr/bin/konsistent")
        assert resolve_konsistent_argv(konsistent_bin=None) == ["/usr/bin/konsistent"]

    def test_resolve_konsistent_argv_falls_back_to_module_invocation(self, monkeypatch) -> None:
        monkeypatch.setattr(eval_conventions.shutil, "which", lambda _name: None)
        assert resolve_konsistent_argv(konsistent_bin=None) == [sys.executable, "-m", "konsistent"]


class TestBuildCheckArgv:
    def test_build_check_argv_minimal(self) -> None:
        argv = build_check_argv(
            base_argv=["konsistent"],
            config_path=None,
            diagnostic_level=None,
            placeholders=[],
            max_diagnostics=1_000_000,
            extra_args=[],
        )
        assert argv == ["konsistent", "check", "--format", "json", "--max-diagnostics", "1000000"]

    def test_build_check_argv_with_all_options(self) -> None:
        argv = build_check_argv(
            base_argv=["konsistent"],
            config_path="/x/konsistent.json",
            diagnostic_level="error",
            placeholders=["team:foo", "x:y"],
            max_diagnostics=500,
            extra_args=["--show-suppressed"],
        )
        assert argv == [
            "konsistent",
            "check",
            "--format",
            "json",
            "--max-diagnostics",
            "500",
            "--config-path",
            "/x/konsistent.json",
            "--diagnostic-level",
            "error",
            "--placeholder",
            "team:foo",
            "--placeholder",
            "x:y",
            "--show-suppressed",
        ]


class TestParseCheckJson:
    def test_parse_check_json_valid(self) -> None:
        stdout = (
            '{"diagnostics":[],"suppressed":[],"summary":'
            '{"filesChecked":0,"errors":0,"warnings":0,"suppressed":0,"durationMs":1.0}}'
        )
        raw = parse_check_json(stdout=stdout)
        assert raw == json.loads(stdout)

    def test_parse_check_json_invalid_json_raises(self) -> None:
        try:
            parse_check_json(stdout="not json")
        except EvalError as exc:
            assert "not json" in str(exc)
        else:
            raise AssertionError("expected EvalError")

    def test_parse_check_json_missing_required_keys_raises(self) -> None:
        try:
            parse_check_json(stdout='{"foo":1}')
        except EvalError as exc:
            message = str(exc)
            assert "diagnostics" in message
            assert "summary" in message
        else:
            raise AssertionError("expected EvalError")


class TestSummarize:
    def test_summarize_counts_by_severity_convention_predicate(self) -> None:
        raw = {
            "diagnostics": [
                {
                    "filePath": "a.py",
                    "severity": "error",
                    "conventionName": "conv-a",
                    "predicateName": "haveType",
                },
                {
                    "filePath": "b.py",
                    "severity": "warning",
                    "conventionName": "conv-b",
                    "predicateName": "haveDocstrings",
                },
                {
                    "filePath": "c.py",
                    "severity": "error",
                    "conventionName": None,
                    "predicateName": "mustNot.import",
                },
                {
                    "filePath": "d.py",
                    "severity": "error",
                    "conventionName": "unused-code",
                    "predicateName": "unusedCode.dead",
                },
                {
                    "filePath": "e.py",
                    "severity": "warning",
                    "conventionName": "unused-code",
                    "predicateName": "unusedCode.testOnly",
                },
            ],
            "summary": {
                "filesChecked": 5,
                "errors": 3,
                "warnings": 2,
                "suppressed": 0,
                "durationMs": 10.0,
            },
        }
        summary = summarize(raw=raw)
        assert summary["bySeverity"] == {"error": 3, "warning": 2}
        assert summary["byConvention"] == {
            "(none)": 1,
            "conv-a": 1,
            "conv-b": 1,
            "unused-code": 2,
        }
        assert summary["byPredicate"] == {
            "haveDocstrings": 1,
            "haveType": 1,
            "mustNot.import": 1,
            "unusedCode.dead": 1,
            "unusedCode.testOnly": 1,
        }
        assert summary["unusedCode"] == {"dead": 1, "testOnly": 1, "total": 2}

    def test_summarize_empty_diagnostics_returns_zeroed_shape(self) -> None:
        raw = {"diagnostics": [], "summary": {}}
        summary = summarize(raw=raw)
        assert summary["byConvention"] == {}
        assert summary["byPredicate"] == {}
        assert summary["unusedCode"] == {"dead": 0, "testOnly": 0, "total": 0}
        assert summary["topFiles"] == []

    def test_summarize_ignores_unknown_extra_diagnostic_keys(self) -> None:
        raw = {
            "diagnostics": [
                {
                    "filePath": "a.py",
                    "severity": "error",
                    "conventionName": "conv-a",
                    "predicateName": "haveType",
                    "fixHint": {"suggestion": "do the thing"},
                }
            ],
            "summary": {},
        }
        summary = summarize(raw=raw)
        assert "fixHint" not in json.dumps(summary)

    def test_summarize_defaults_missing_severity_and_predicate_name(self) -> None:
        raw = {
            "diagnostics": [
                {"filePath": "a.py", "conventionName": "conv-a"},
            ],
            "summary": {},
        }
        summary = summarize(raw=raw)
        assert summary["bySeverity"] == {"error": 1}
        assert summary["byPredicate"] == {"(unknown)": 1}

    def test_summarize_top_files_ordering_and_tie_break(self) -> None:
        diagnostics = []
        for _ in range(5):
            diagnostics.append({"filePath": "z.py"})
        for _ in range(5):
            diagnostics.append({"filePath": "a.py"})
        for _ in range(2):
            diagnostics.append({"filePath": "m.py"})
        raw = {"diagnostics": diagnostics, "summary": {}}

        summary = summarize(raw=raw)
        assert summary["topFiles"] == [
            {"filePath": "a.py", "count": 5},
            {"filePath": "z.py", "count": 5},
            {"filePath": "m.py", "count": 2},
        ]

        summary_top1 = summarize(raw=raw, top_files=1)
        assert summary_top1["topFiles"] == [{"filePath": "a.py", "count": 5}]


class TestBuildMetrics:
    def test_build_metrics_success_path(self, tmp_path: Path) -> None:
        stdout = json.dumps(
            {
                "diagnostics": [
                    {
                        "filePath": "a.py",
                        "severity": "error",
                        "conventionName": "c",
                        "predicateName": "p",
                    },
                    {
                        "filePath": "b.py",
                        "severity": "warning",
                        "conventionName": "c",
                        "predicateName": "p",
                    },
                ],
                "summary": {
                    "filesChecked": 2,
                    "errors": 1,
                    "warnings": 1,
                    "suppressed": 0,
                    "durationMs": 5.0,
                },
            }
        )
        runner = _fake_runner(_outcome(exit_code=1, stdout=stdout))
        metrics = build_metrics(
            target_repo=tmp_path,
            config_path=None,
            konsistent_bin="konsistent",
            diagnostic_level=None,
            placeholders=[],
            max_diagnostics=1_000_000,
            extra_args=[],
            label="mylabel",
            top_files=10,
            timeout_seconds=30.0,
            runner=runner,
        )
        assert metrics["schemaVersion"] == 1
        assert metrics["meta"]["exitCode"] == 1
        assert metrics["meta"]["command"] == runner.calls[0][0]  # type: ignore[attr-defined]
        assert metrics["meta"]["label"] == "mylabel"
        assert metrics["meta"]["targetRepo"] == str(tmp_path.resolve())

        raw = json.loads(stdout)
        expected_summary = summarize(raw=raw, top_files=10)
        for key in (
            "summary",
            "bySeverity",
            "byConvention",
            "byPredicate",
            "unusedCode",
            "topFiles",
        ):
            assert metrics[key] == expected_summary[key]

    def test_build_metrics_success_path_label_none(self, tmp_path: Path) -> None:
        runner = _fake_runner(_outcome())
        metrics = build_metrics(
            target_repo=tmp_path,
            config_path=None,
            konsistent_bin="konsistent",
            diagnostic_level=None,
            placeholders=[],
            max_diagnostics=1_000_000,
            extra_args=[],
            label=None,
            top_files=10,
            timeout_seconds=30.0,
            runner=runner,
        )
        assert metrics["meta"]["label"] is None

    def test_build_metrics_raises_on_unparseable_output(self, tmp_path: Path) -> None:
        runner = _fake_runner(_outcome(stdout="garbage", exit_code=1, stderr="boom"))
        try:
            build_metrics(
                target_repo=tmp_path,
                config_path=None,
                konsistent_bin="konsistent",
                diagnostic_level=None,
                placeholders=[],
                max_diagnostics=1_000_000,
                extra_args=[],
                label=None,
                top_files=10,
                timeout_seconds=30.0,
                runner=runner,
            )
        except EvalError as exc:
            message = str(exc)
            assert "boom" in message
            assert "exit_code=1" in message
        else:
            raise AssertionError("expected EvalError")

    def test_build_metrics_raises_on_timeout(self, tmp_path: Path) -> None:
        runner = _fake_runner(
            RunOutcome(timed_out=True, exit_code=-1, stdout="", stderr="", wall_clock_ms=1.0)
        )
        try:
            build_metrics(
                target_repo=tmp_path,
                config_path=None,
                konsistent_bin="konsistent",
                diagnostic_level=None,
                placeholders=[],
                max_diagnostics=1_000_000,
                extra_args=[],
                label=None,
                top_files=10,
                timeout_seconds=17.0,
                runner=runner,
            )
        except EvalError as exc:
            message = str(exc)
            assert "timed out" in message
            assert "17.0" in message
        else:
            raise AssertionError("expected EvalError")

    def test_build_metrics_rejects_nonexistent_target_repo(self, tmp_path: Path) -> None:
        runner = _fake_runner(_outcome())
        missing = tmp_path / "does-not-exist"
        try:
            build_metrics(
                target_repo=missing,
                config_path=None,
                konsistent_bin="konsistent",
                diagnostic_level=None,
                placeholders=[],
                max_diagnostics=1_000_000,
                extra_args=[],
                label=None,
                top_files=10,
                timeout_seconds=30.0,
                runner=runner,
            )
        except EvalError:
            pass
        else:
            raise AssertionError("expected EvalError")
        assert len(runner.calls) == 0  # type: ignore[attr-defined]


def _summary_dict(
    *,
    errors: int,
    warnings: int,
    files_checked: int = 1,
    suppressed: int = 0,
    duration_ms: float | None = 1.0,
    label: str | None = None,
) -> dict:
    return {
        "schemaVersion": 1,
        "meta": {
            "label": label,
            "targetRepo": "/x",
            "command": [],
            "exitCode": 0,
            "durationMsWallClock": 1.0,
            "generatedAt": "now",
            "configPath": None,
        },
        "summary": {
            "filesChecked": files_checked,
            "totalDiagnostics": errors + warnings,
            "errors": errors,
            "warnings": warnings,
            "suppressed": suppressed,
            "konsistentDurationMs": duration_ms,
        },
        "bySeverity": {},
        "byConvention": {},
        "byPredicate": {},
        "unusedCode": {"dead": 0, "testOnly": 0, "total": 0},
        "topFiles": [],
    }


class TestCompareSummaries:
    def test_compare_summaries_basic_delta(self) -> None:
        before = _summary_dict(
            errors=10, warnings=5, files_checked=100, suppressed=2, duration_ms=100.0
        )
        after = _summary_dict(
            errors=6, warnings=3, files_checked=110, suppressed=2, duration_ms=80.0
        )
        comparison = compare_summaries(before=before, after=after)
        assert comparison["summary"]["errors"] == {"before": 10, "after": 6, "delta": -4}
        assert comparison["summary"]["warnings"] == {"before": 5, "after": 3, "delta": -2}
        assert comparison["summary"]["filesChecked"] == {"before": 100, "after": 110, "delta": 10}
        assert comparison["summary"]["suppressed"] == {"before": 2, "after": 2, "delta": 0}
        assert comparison["summary"]["totalDiagnostics"] == {"before": 15, "after": 9, "delta": -6}

    def test_compare_summaries_unions_convention_and_predicate_keys(self) -> None:
        before = _summary_dict(errors=1, warnings=0)
        after = _summary_dict(errors=1, warnings=0)
        before["byConvention"] = {"a": 3}
        after["byConvention"] = {"b": 2}
        comparison = compare_summaries(before=before, after=after)
        assert comparison["byConvention"] == {
            "a": {"before": 3, "after": 0, "delta": -3},
            "b": {"before": 0, "after": 2, "delta": 2},
        }

    def test_compare_summaries_treats_null_duration_as_zero_for_delta_but_preserves_raw(
        self,
    ) -> None:
        before = _summary_dict(errors=0, warnings=0, duration_ms=None)
        after = _summary_dict(errors=0, warnings=0, duration_ms=50.0)
        comparison = compare_summaries(before=before, after=after)
        entry = comparison["summary"]["konsistentDurationMs"]
        assert entry["before"] is None
        assert entry["after"] == 50.0
        assert entry["delta"] == 50.0

    def test_compare_summaries_rejects_schema_version_mismatch(self) -> None:
        before = _summary_dict(errors=0, warnings=0)
        after = _summary_dict(errors=0, warnings=0)
        after["schemaVersion"] = 2
        try:
            compare_summaries(before=before, after=after)
        except EvalError:
            pass
        else:
            raise AssertionError("expected EvalError")


class TestDetectRegression:
    def test_detect_regression_true_when_errors_increase(self) -> None:
        assert detect_regression(before_errors=1, after_errors=2) is True

    def test_detect_regression_false_when_equal_or_decrease(self) -> None:
        assert detect_regression(before_errors=2, after_errors=2) is False
        assert detect_regression(before_errors=2, after_errors=1) is False


class TestFormatCompareTable:
    def test_format_compare_table_contains_expected_lines(self) -> None:
        before = _summary_dict(errors=10, warnings=5, label="before")
        after = _summary_dict(errors=6, warnings=3, label="after")
        before["byConvention"] = {"conv-a": 5}
        after["byConvention"] = {"conv-a": 2}
        comparison = compare_summaries(before=before, after=after)
        table = format_compare_table(comparison=comparison)
        assert "errors" in table
        assert "->" in table
        assert "conv-a" in table
        assert "Regression check:" in table


class TestCli:
    def test_cli_run_writes_json_to_output_file(self, tmp_path: Path, monkeypatch) -> None:
        out_file = tmp_path / "out.json"
        stdout = json.dumps(
            {
                "diagnostics": [],
                "summary": {
                    "filesChecked": 0,
                    "errors": 0,
                    "warnings": 0,
                    "suppressed": 0,
                    "durationMs": None,
                },
            }
        )
        monkeypatch.setattr(
            eval_conventions,
            "run_konsistent_check",
            lambda argv, cwd, timeout_seconds: _outcome(stdout=stdout),
        )
        code = main(["run", str(tmp_path), "--output", str(out_file)])
        assert code == 0
        parsed = json.loads(out_file.read_text(encoding="utf-8"))
        assert parsed["schemaVersion"] == 1
        assert parsed["summary"]["filesChecked"] == 0

    def test_cli_run_prints_to_stdout_when_no_output_given(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        stdout = json.dumps(
            {
                "diagnostics": [],
                "summary": {
                    "filesChecked": 0,
                    "errors": 0,
                    "warnings": 0,
                    "suppressed": 0,
                    "durationMs": None,
                },
            }
        )
        monkeypatch.setattr(
            eval_conventions,
            "run_konsistent_check",
            lambda argv, cwd, timeout_seconds: _outcome(stdout=stdout),
        )
        code = main(["run", str(tmp_path)])
        assert code == 0
        out = capsys.readouterr().out
        json.loads(out)

    def test_cli_run_returns_2_on_eval_error(self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.setattr(
            eval_conventions,
            "run_konsistent_check",
            lambda argv, cwd, timeout_seconds: _outcome(stdout="garbage", exit_code=1),
        )
        code = main(["run", str(tmp_path)])
        assert code == 2
        assert capsys.readouterr().err

    def test_cli_run_rejects_nonexistent_target(self, tmp_path: Path, monkeypatch) -> None:
        calls = []
        monkeypatch.setattr(
            eval_conventions,
            "run_konsistent_check",
            lambda argv, cwd, timeout_seconds: calls.append(1) or _outcome(),
        )
        code = main(["run", str(tmp_path / "does-not-exist")])
        assert code == 2
        assert len(calls) == 0

    def test_cli_compare_table_format_default(self, tmp_path: Path, capsys) -> None:
        before = tmp_path / "before.json"
        after = tmp_path / "after.json"
        before.write_text(json.dumps(_summary_dict(errors=5, warnings=1)), encoding="utf-8")
        after.write_text(json.dumps(_summary_dict(errors=2, warnings=1)), encoding="utf-8")
        code = main(["compare", str(before), str(after)])
        assert code == 0
        out = capsys.readouterr().out
        assert "Regression check:" in out

    def test_cli_compare_json_format(self, tmp_path: Path, capsys) -> None:
        before = tmp_path / "before.json"
        after = tmp_path / "after.json"
        before_dict = _summary_dict(errors=5, warnings=1)
        after_dict = _summary_dict(errors=2, warnings=1)
        before.write_text(json.dumps(before_dict), encoding="utf-8")
        after.write_text(json.dumps(after_dict), encoding="utf-8")
        code = main(["compare", str(before), str(after), "--format", "json"])
        assert code == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed == compare_summaries(before=before_dict, after=after_dict)

    def test_cli_compare_fail_on_regression_exit_code(self, tmp_path: Path, capsys) -> None:
        before = tmp_path / "before.json"
        after = tmp_path / "after.json"
        before.write_text(json.dumps(_summary_dict(errors=2, warnings=0)), encoding="utf-8")
        after.write_text(json.dumps(_summary_dict(errors=5, warnings=0)), encoding="utf-8")

        code = main(["compare", str(before), str(after), "--fail-on-regression"])
        assert code == 1

        code_no_flag = main(["compare", str(before), str(after)])
        assert code_no_flag == 0

    def test_cli_compare_missing_file_returns_2(self, tmp_path: Path) -> None:
        after = tmp_path / "after.json"
        after.write_text(json.dumps(_summary_dict(errors=0, warnings=0)), encoding="utf-8")
        code = main(["compare", "/no/such/file.json", str(after)])
        assert code == 2

    def test_main_no_command_prints_usage_and_returns_2(self, capsys) -> None:
        try:
            main([])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("expected SystemExit from argparse required subparsers")


class TestArgParser:
    def test_build_arg_parser_smoke(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(["run", "."])
        assert args.command == "run"
        assert args.max_diagnostics == eval_conventions.DEFAULT_MAX_DIAGNOSTICS


class TestRealSubprocessSmoke:
    def test_run_konsistent_check_real_subprocess_smoke(self, tmp_path: Path) -> None:
        (tmp_path / "konsistent.json").write_text(
            json.dumps({"version": "v1", "conventions": []}), encoding="utf-8"
        )
        argv = [
            *resolve_konsistent_argv(konsistent_bin=None),
            "check",
            "--format",
            "json",
            "--max-diagnostics",
            "1000000",
        ]
        outcome = run_konsistent_check(argv, tmp_path, 30.0)
        assert outcome.timed_out is False
        assert outcome.exit_code == 0
        parsed = json.loads(outcome.stdout)
        assert parsed["diagnostics"] == []
        assert parsed["summary"]["filesChecked"] >= 0
