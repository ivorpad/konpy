from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from konpy.cli.app import _preprocess_argv, app
from konpy.cli.gate import run_gate_command
from konpy.core.filesystem import FakeFileSystem
from konpy.core.runner import RunResult

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_config(tmp_path: Path, conventions: list[dict[str, object]]) -> None:
    write_json(tmp_path / "konpy.json", {"version": "v1", "conventions": conventions})


def payload_json(
    *,
    tool_name: str | None = "Write",
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = "/project",
) -> str:
    return json.dumps(
        {
            "tool_name": tool_name,
            "tool_input": {} if tool_input is None else tool_input,
            "cwd": cwd,
        }
    )


def write_payload(*, file_path: str = "src/service.py", content: str = "") -> str:
    return payload_json(
        tool_name="Write",
        tool_input={"file_path": file_path, "content": content},
    )


def make_export_config(tmp_path: Path, *, severity: str | None = None) -> None:
    convention: dict[str, object] = {
        "name": "service-must-export-process",
        "paths": "src/service.py",
        "must": {"export": ["process"]},
    }
    if severity is not None:
        convention["severity"] = severity
    write_config(tmp_path, [convention])


class TestGateSkips:
    def test_blank_payload_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text="   ",
            file_system=FakeFileSystem(),
        )

        assert exit_code == 0

    def test_invalid_payload_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text="not json",
            file_system=FakeFileSystem(),
        )

        assert exit_code == 0

    def test_non_claude_tool_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(tool_name="Bash", tool_input={"command": "ls"}),
            file_system=FakeFileSystem(),
        )

        assert exit_code == 0

    def test_non_matching_path_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=["tests/**/*.py"],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        assert exit_code == 0

    def test_apply_patch_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": "*** Update File: src/service.py\n"},
            ),
            file_system=FakeFileSystem(),
        )

        assert exit_code == 0

    def test_unreconstructable_edit_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/service.py",
                    "old_string": "missing",
                    "new_string": "new",
                },
            ),
            file_system=FakeFileSystem(contents={"src/service.py": "old\n"}),
        )

        assert exit_code == 0


class TestGateExitContract:
    def test_clean_proposed_write_exits_zero_silently(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="def process():\n    return 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == ""
        assert captured.err == ""

    def test_error_diagnostic_exits_two_with_json_on_stderr(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        parsed = json.loads(captured.err)
        assert exit_code == 2
        assert captured.out == ""
        assert parsed["diagnostics"][0]["filePath"] == "src/service.py"
        assert parsed["diagnostics"][0]["conventionName"] == "service-must-export-process"
        assert parsed["diagnostics"][0]["predicateName"] == "export"
        assert parsed["summary"]["errors"] == 1
        assert parsed["truncation"] == {"shown": 1, "omitted": 0}

    def test_omitted_match_gates_all_target_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        assert exit_code == 2

    def test_warnings_only_exit_zero_without_error_on_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path, severity="warning")
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""

    def test_warnings_only_exit_two_with_error_on_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path, severity="warning")
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=True,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        parsed = json.loads(captured.err)
        assert exit_code == 2
        assert parsed["summary"]["warnings"] == 1

    def test_diagnostic_level_error_skips_warning_conventions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path, severity="warning")
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="error",
            error_on_warnings=True,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""


class TestGateFailOpen:
    def test_config_load_error_exits_zero_with_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err.startswith("konpy gate: warning:")

    def test_runner_exception_exits_zero_with_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        def boom(**_kwargs):
            raise RuntimeError("runner failed")

        monkeypatch.setattr("konpy.cli.gate.run", boom)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "konpy gate: warning: runner failed" in captured.err

    def test_konpy_hook_active_does_not_disable_gate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KONPY_HOOK_ACTIVE", "1")

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
        )

        assert exit_code == 2


class TestGateFailClosedSkipsBothModes:
    """Rows the spec pins to `skip` regardless of --fail-closed."""

    def test_non_claude_tool_exits_zero_fail_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(tool_name="Bash", tool_input={"command": "ls"}),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        assert exit_code == 0

    def test_non_matching_path_exits_zero_fail_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=["tests/**/*.py"],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        assert exit_code == 0


class TestGateFailClosedVerificationUnavailable:
    """Rows the spec flips from `skip` to `verification-unavailable` under --fail-closed."""

    def _assert_verification_unavailable(self, captured_err: str) -> None:
        assert captured_err.startswith("konpy gate: verification unavailable: ")
        assert captured_err.rstrip("\n").endswith("(blocking: --fail-closed)")
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured_err)

    def test_blank_payload_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text="   ",
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        self._assert_verification_unavailable(captured.err)

    def test_invalid_payload_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text="not json",
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        self._assert_verification_unavailable(captured.err)

    def test_supported_tool_without_target_path_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(tool_name="Write", tool_input={"content": "VALUE = 1\n"}),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        self._assert_verification_unavailable(captured.err)

    def test_unreconstructable_edit_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=payload_json(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/service.py",
                    "old_string": "missing",
                    "new_string": "new",
                },
            ),
            file_system=FakeFileSystem(contents={"src/service.py": "old\n"}),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        self._assert_verification_unavailable(captured.err)

    def test_config_load_error_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        self._assert_verification_unavailable(captured.err)

    def test_runner_exception_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        def boom(**_kwargs):
            raise RuntimeError("runner failed")

        monkeypatch.setattr("konpy.cli.gate.run", boom)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert "runner failed" in captured.err
        self._assert_verification_unavailable(captured.err)


class TestGateFailClosedViolationAndPass:
    """Violation and pass rows are unchanged by --fail-closed."""

    def test_violation_exits_two_with_same_diagnostics_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="VALUE = 1\n"),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        parsed = json.loads(captured.err)
        assert exit_code == 2
        assert parsed["diagnostics"][0]["conventionName"] == "service-must-export-process"
        assert parsed["summary"]["errors"] == 1

    def test_clean_proposed_write_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="def process():\n    return 1\n"),
            file_system=FakeFileSystem(),
            fail_closed=True,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out == ""
        assert captured.err == ""


class TestGateUnusedCodePerf:
    """`unusedCode` is a whole-project scan -- gate must skip it by default and
    only pay for it when `--error-on-warnings` means it could actually block."""

    def _spy_on_run(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        captured_kwargs: dict[str, object] = {}

        def spy(**kwargs: object) -> RunResult:
            captured_kwargs.update(kwargs)
            return RunResult(diagnostics=[], files_checked=0, duration_ms=0.0)

        monkeypatch.setattr("konpy.cli.gate.run", spy)
        return captured_kwargs

    def test_default_run_disables_unused_code_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        captured_kwargs = self._spy_on_run(monkeypatch)

        run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=False,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="def process():\n    return 1\n"),
            file_system=FakeFileSystem(),
        )

        assert captured_kwargs["run_unused_code"] is False

    def test_error_on_warnings_enables_unused_code_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_export_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        captured_kwargs = self._spy_on_run(monkeypatch)

        run_gate_command(
            match=[],
            config_path=None,
            config_package=None,
            diagnostic_level="warning",
            error_on_warnings=True,
            placeholder=None,
            max_diagnostics=100,
            stdin_text=write_payload(content="def process():\n    return 1\n"),
            file_system=FakeFileSystem(),
        )

        assert captured_kwargs["run_unused_code"] is True


class TestGateCliWiring:
    def test_gate_is_routed_unchanged_by_preprocess_argv(self) -> None:
        argv = ["gate", "--match", "src/**/*.py"]
        assert _preprocess_argv(argv) == argv

    def test_unknown_option_exits_one_not_two(self) -> None:
        result = runner.invoke(
            app,
            ["gate", "--bogus-flag", "x"],
            input="{}",
        )

        assert result.exit_code == 1
        assert "--bogus-flag" in result.stderr

    def test_gate_command_accepts_empty_payload(self) -> None:
        result = runner.invoke(app, ["gate"], input="")

        assert result.exit_code == 0

    def test_fail_closed_flag_blocks_unparseable_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["gate", "--fail-closed"], input="not json")

        assert result.exit_code == 2
        assert "konpy gate: verification unavailable:" in result.stderr

    def test_default_mode_still_fails_open_on_unparseable_payload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["gate"], input="not json")

        assert result.exit_code == 0
