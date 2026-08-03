"""Tests for `konpy.core._report_tools` (external-tool lanes)."""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path

from konpy.core._report_tools import (
    STATUS_LABEL,
    _basedpyright_lane,
    _has_import_linter_config,
    _import_linter_lane,
    _ruff_lane,
    collect_tool_lanes,
)


def _completed(
    argv: Sequence[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=list(argv), returncode=returncode, stdout=stdout, stderr=stderr
    )


class _FakeRunner:
    """A canned `runner` stand-in: records calls, returns/raises what's configured."""

    def __init__(
        self,
        result: subprocess.CompletedProcess[str] | None = None,
        exc: BaseException | None = None,
    ) -> None:
        self.result = result
        self.exc = exc
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


_RUFF_JSON = [
    {"code": "E501", "message": "line too long (105 > 100 characters)"},
    {"code": "E501", "message": "line too long (110 > 100 characters)"},
    {"code": "F401", "message": "`os` imported but unused"},
]

_BASEDPYRIGHT_JSON = {
    "summary": {"errorCount": 1, "warningCount": 2, "informationCount": 0},
    "generalDiagnostics": [
        {"rule": "reportGeneralTypeIssues", "message": "bad"},
        {"rule": "reportGeneralTypeIssues", "message": "bad2"},
        {"rule": "reportMissingImports", "message": "missing"},
    ],
}


class TestRuffLane:
    def test_ok_ranks_and_caps_top_items(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], stdout=json.dumps(_RUFF_JSON)))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "ok"
        assert lane.findings == 3
        assert lane.top_items[0] == "E501 x2  line too long (105 > 100 characters)"
        assert lane.top_items[1].startswith("F401 x1")

    def test_top_items_capped_at_five_with_remainder_note(self, tmp_path: Path) -> None:
        findings = [{"code": f"E{i}", "message": "msg"} for i in range(7)]
        runner = _FakeRunner(_completed(["ruff"], stdout=json.dumps(findings)))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.findings == 7
        assert len(lane.top_items) == 6
        assert lane.top_items[-1] == "... and 2 more"

    def test_untruncated_breakdown_has_no_remainder_note(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], stdout=json.dumps(_RUFF_JSON)))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert not any(item.startswith("... and") for item in lane.top_items)

    def test_prefers_target_venv_executable(self, tmp_path: Path) -> None:
        venv_ruff = tmp_path / ".venv" / "bin" / "ruff"
        venv_ruff.parent.mkdir(parents=True)
        venv_ruff.write_text("#!/bin/sh\n", encoding="utf-8")
        venv_ruff.chmod(0o755)
        runner = _FakeRunner(_completed(["ruff"], stdout="[]"))

        _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert runner.calls[0][0] == str(venv_ruff)

    def test_falls_back_to_path_lookup_without_a_venv(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], stdout="[]"))

        _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert runner.calls[0][0] == "ruff"

    def test_message_is_truncated(self, tmp_path: Path) -> None:
        long_message = "x" * 200
        runner = _FakeRunner(
            _completed(["ruff"], stdout=json.dumps([{"code": "E1", "message": long_message}]))
        )

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert len(lane.top_items[0]) < len(long_message)
        assert lane.top_items[0].endswith("...")

    def test_not_installed(self, tmp_path: Path) -> None:
        runner = _FakeRunner(exc=FileNotFoundError())

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "not-installed"
        assert lane.note is not None and "konpy[quality]" in lane.note
        assert lane.findings == 0
        assert lane.top_items == ()

    def test_timed_out(self, tmp_path: Path) -> None:
        runner = _FakeRunner(exc=subprocess.TimeoutExpired(cmd=["ruff"], timeout=5))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "timed-out"

    def test_unexpected_exit_code_is_an_error(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], returncode=2, stderr="boom\nmore detail"))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "error"
        assert lane.note == "boom"

    def test_unparsable_output_is_an_error(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], returncode=0, stdout="not json"))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "error"

    def test_exit_code_one_is_ok(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["ruff"], returncode=1, stdout=json.dumps(_RUFF_JSON)))

        lane = _ruff_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "ok"


class TestBasedpyrightLane:
    def test_ok_findings_is_error_plus_warning_count(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["basedpyright"], stdout=json.dumps(_BASEDPYRIGHT_JSON)))

        lane = _basedpyright_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "ok"
        assert lane.findings == 3
        assert lane.top_items[0] == "reportGeneralTypeIssues x2"
        assert lane.top_items[1] == "reportMissingImports x1"

    def test_diagnostic_without_a_rule_falls_back_to_other(self, tmp_path: Path) -> None:
        payload = {
            "summary": {"errorCount": 1, "warningCount": 0},
            "generalDiagnostics": [{"message": "syntax error"}],
        }
        runner = _FakeRunner(_completed(["basedpyright"], stdout=json.dumps(payload)))

        lane = _basedpyright_lane(tmp_path, timeout=5, runner=runner)

        assert lane.top_items == ("other x1",)

    def test_not_installed(self, tmp_path: Path) -> None:
        runner = _FakeRunner(exc=FileNotFoundError())

        lane = _basedpyright_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "not-installed"

    def test_timed_out(self, tmp_path: Path) -> None:
        runner = _FakeRunner(exc=subprocess.TimeoutExpired(cmd=["basedpyright"], timeout=5))

        lane = _basedpyright_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "timed-out"

    def test_error_status_carries_stderr_first_line(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["basedpyright"], returncode=2, stderr="fatal: boom\n"))

        lane = _basedpyright_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "error"
        assert lane.note == "fatal: boom"


class TestHasImportLinterConfig:
    def test_no_config_anywhere(self, tmp_path: Path) -> None:
        assert _has_import_linter_config(tmp_path) is False

    def test_pyproject_tool_importlinter_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.importlinter]\nroot_package = "x"\n', encoding="utf-8"
        )
        assert _has_import_linter_config(tmp_path) is True

    def test_pyproject_without_importlinter_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.ruff]\nline-length = 100\n', encoding="utf-8"
        )
        assert _has_import_linter_config(tmp_path) is False

    def test_malformed_pyproject_does_not_raise(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("not [ valid toml", encoding="utf-8")
        assert _has_import_linter_config(tmp_path) is False

    def test_setup_cfg_importlinter_section(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text(
            "[importlinter]\nroot_package = x\n", encoding="utf-8"
        )
        assert _has_import_linter_config(tmp_path) is True

    def test_dot_importlinter_file(self, tmp_path: Path) -> None:
        (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
        assert _has_import_linter_config(tmp_path) is True


class TestImportLinterLane:
    def test_no_config_never_invokes_the_runner(self, tmp_path: Path) -> None:
        runner = _FakeRunner(_completed(["lint-imports"], stdout="should not be called"))

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "no-config"
        assert lane.note is not None and "import-boundaries.md" in lane.note
        assert runner.calls == []

    def test_ok_parses_kept_and_broken_and_lists_broken_contracts(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.importlinter]\nroot_package = "x"\n', encoding="utf-8"
        )
        stdout = (
            "Contracts\n---------\n\n"
            "layer a KEPT\n"
            "layer b BROKEN\n\n"
            "Contracts: 1 kept, 1 broken.\n"
        )
        runner = _FakeRunner(_completed(["lint-imports"], returncode=1, stdout=stdout))

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "ok"
        assert lane.findings == 1
        assert lane.top_items == ("layer b",)
        assert lane.note == "1 kept"

    def test_broken_contracts_beyond_the_cap_get_a_remainder_note(self, tmp_path: Path) -> None:
        (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
        broken_lines = "\n".join(f"layer {i} BROKEN" for i in range(7))
        stdout = f"{broken_lines}\n\nContracts: 0 kept, 7 broken.\n"
        runner = _FakeRunner(_completed(["lint-imports"], returncode=1, stdout=stdout))

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.findings == 7
        assert len(lane.top_items) == 6
        assert lane.top_items[-1] == "... and 2 more"

    def test_not_installed(self, tmp_path: Path) -> None:
        (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
        runner = _FakeRunner(exc=FileNotFoundError())

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "not-installed"

    def test_timed_out(self, tmp_path: Path) -> None:
        (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
        runner = _FakeRunner(exc=subprocess.TimeoutExpired(cmd=["lint-imports"], timeout=5))

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "timed-out"

    def test_unparsable_summary_is_an_error(self, tmp_path: Path) -> None:
        (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
        runner = _FakeRunner(_completed(["lint-imports"], returncode=1, stdout="a traceback\n"))

        lane = _import_linter_lane(tmp_path, timeout=5, runner=runner)

        assert lane.status == "error"


class TestStatusLabel:
    def test_every_status_has_a_label(self) -> None:
        for status in ("ok", "not-installed", "no-config", "timed-out", "error"):
            assert status in STATUS_LABEL


class TestCollectToolLanes:
    def test_returns_ruff_basedpyright_import_linter_in_that_order(self, tmp_path: Path) -> None:
        def runner(argv: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
            if argv[0] == "ruff":
                return _completed(argv, stdout="[]")
            if argv[0] == "basedpyright":
                return _completed(
                    argv,
                    stdout=json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
                )
            raise AssertionError("import-linter should not run without configured contracts")

        lanes = collect_tool_lanes(tmp_path, timeout=5, runner=runner)

        assert [lane.name for lane in lanes] == ["ruff", "basedpyright", "import-linter"]
        assert lanes[2].status == "no-config"

    def test_three_tools_run_concurrently_not_sequentially(self, tmp_path: Path) -> None:
        # A barrier only releases once all three tools have started their
        # subprocess call. A sequential (non-threaded) implementation would
        # deadlock here -- the first call would block forever waiting for two
        # more arrivals that can never come until it returns -- and the
        # barrier's own timeout turns that into a bounded test failure
        # instead of a hang.
        (tmp_path / "pyproject.toml").write_text(
            '[tool.importlinter]\nroot_package = "x"\n', encoding="utf-8"
        )
        barrier = threading.Barrier(3, timeout=5)

        def runner(argv: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
            barrier.wait()
            if argv[0] == "ruff":
                return _completed(argv, stdout="[]")
            if argv[0] == "basedpyright":
                return _completed(
                    argv,
                    stdout=json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
                )
            return _completed(argv, stdout="Contracts: 1 kept, 0 broken.\n")

        lanes = collect_tool_lanes(tmp_path, timeout=5, runner=runner)

        assert all(lane.status == "ok" for lane in lanes)
