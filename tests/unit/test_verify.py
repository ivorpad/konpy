from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify"


def _load_verify_module() -> ModuleType:
    """Load the extensionless `scripts/verify` script as an importable module."""
    loader = SourceFileLoader("konpy_scripts_verify", str(SCRIPT_PATH))
    spec = importlib.util.spec_from_file_location(
        "konpy_scripts_verify", SCRIPT_PATH, loader=loader
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verify() -> ModuleType:
    return _load_verify_module()


class _FakeCompleted:
    """Minimal stand-in for `subprocess.CompletedProcess` in fake runners."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


class TestBuildSteps:
    def test_full_profile_delegates_to_konpy_verify(self, verify: ModuleType) -> None:
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(argv)
            return _FakeCompleted(7)

        exit_code = verify._run_full(REPO_ROOT, env={}, runner=fake_runner)

        assert calls == [
            [sys.executable, "-m", "konpy", "verify", "--config-path", "konpy.json"]
        ]
        assert exit_code == 7

    def test_konpy_json_roster_matches_expected_step_names(self) -> None:
        roster = json.loads((REPO_ROOT / "konpy.json").read_text(encoding="utf-8"))["verify"]

        assert [step["name"] for step in roster["steps"]] == [
            "schema-freshness",
            "guidance-freshness",
            "ruff",
            "basedpyright",
            "import-linter",
            "konpy-validate",
            "konpy-validate-strict",
            "konpy-strict",
            "pytest",
        ]
        by_name = {step["name"]: step["run"] for step in roster["steps"]}
        assert by_name["schema-freshness"] == ["python", "scripts/generate_schema.py", "--check"]
        assert by_name["guidance-freshness"] == ["python", "scripts/verify", "guidance", "--check"]
        assert by_name["ruff"] == ["ruff", "check"]
        assert by_name["konpy-strict"] == [
            "python", "-m", "konpy", "check", "--config-path", "konpy.strict.json",
        ]
        assert by_name["pytest"] == ["python", "-m", "pytest", "-q"]

    def test_release_first_phase_is_the_full_delegation(self, verify: ModuleType) -> None:
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(argv)
            return _FakeCompleted(0)

        verify._run_release(REPO_ROOT, env={}, runner=fake_runner)

        assert calls[0] == [
            sys.executable, "-m", "konpy", "verify", "--config-path", "konpy.json",
        ]

    def test_fast_profile_with_changed_files(
        self, verify: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            verify,
            "_discover_changed_python_files",
            lambda repo_root: ["src/konpy/foo.py", "tests/unit/test_foo.py"],
        )

        steps = verify.build_steps("fast", REPO_ROOT)

        assert [step.name for step in steps] == ["ruff", "konpy-check-changed"]
        assert steps[0].argv == (
            "ruff",
            "check",
            "src/konpy/foo.py",
            "tests/unit/test_foo.py",
        )
        assert steps[1].argv == (sys.executable, "-m", "konpy", "check", "--changed")

    def test_fast_profile_skips_ruff_when_nothing_changed(
        self, verify: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(verify, "_discover_changed_python_files", lambda repo_root: [])

        steps = verify.build_steps("fast", REPO_ROOT)

        assert [step.name for step in steps] == ["konpy-check-changed"]

    def test_hook_pre_profile_step(self, verify: ModuleType) -> None:
        steps = verify.build_steps("hook-pre", REPO_ROOT)

        assert [step.name for step in steps] == ["hook-pre"]
        assert steps[0].argv == (
            sys.executable,
            "-m",
            "konpy",
            "gate",
            "--fail-closed",
            "--ruff",
            "--config-path",
            "konpy.strict.json",
        )

    def test_no_step_argv_ever_names_an_agent_binary(
        self, verify: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            verify, "_discover_changed_python_files", lambda repo_root: ["src/konpy/foo.py"]
        )

        for profile in ("fast", "hook-pre"):
            for step in verify.build_steps(profile, REPO_ROOT):
                assert "claude" not in step.argv
                assert "codex" not in step.argv

        roster = json.loads((REPO_ROOT / "konpy.json").read_text(encoding="utf-8"))["verify"]
        for roster_step in roster["steps"]:
            assert "claude" not in roster_step["run"]
            assert "codex" not in roster_step["run"]


class TestRunSteps:
    def test_full_aggregation_reports_all_failed_steps(
        self, verify: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        steps = [
            verify.Step("one", ("true",)),
            verify.Step("two", ("false",)),
            verify.Step("three", ("true",)),
            verify.Step("four", ("false",)),
        ]
        returncodes = {"one": 0, "two": 1, "three": 0, "four": 1}

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            name = next(step.name for step in steps if list(step.argv) == argv)
            return _FakeCompleted(returncodes[name])

        results = verify._run_steps(steps, cwd=REPO_ROOT, env={}, runner=fake_runner)
        failed = [result.name for result in results if not result.ok]

        assert failed == ["two", "four"]

        out = capsys.readouterr().out
        assert "[verify] two ... FAILED" in out
        assert "[verify] four ... FAILED" in out
        assert "[verify] one ... ok" in out

    def test_file_not_found_runner_is_reported_not_raised(self, verify: ModuleType) -> None:
        step = verify.Step("missing-tool", ("does-not-exist",))

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            raise FileNotFoundError("does-not-exist")

        result = verify._execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result.ok is False
        assert result.message is not None
        assert "executable not found" in result.message


class TestRunRelease:
    def test_short_circuits_before_building_on_full_step_failure(
        self, verify: ModuleType
    ) -> None:
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(argv)
            if "verify" in argv:
                return _FakeCompleted(1)
            return _FakeCompleted(0)

        exit_code = verify._run_release(REPO_ROOT, env={}, runner=fake_runner)

        assert exit_code == 1
        assert not any(argv[:2] == ["uv", "build"] for argv in calls)
        assert not any(argv[:1] == ["twine"] for argv in calls)

    def test_twine_check_gets_only_wheel_and_sdist(
        self, verify: ModuleType, tmp_path: Path
    ) -> None:
        # `uv build` drops a `.gitignore` into a dist/ it creates; twine
        # rejects any non-distribution file, so the glob must skip it.
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            calls.append(argv)
            if argv[:2] == ["uv", "build"]:
                dist = tmp_path / "dist"
                dist.mkdir()
                (dist / "pkg-0.7.0-py3-none-any.whl").write_bytes(b"")
                (dist / "pkg-0.7.0.tar.gz").write_bytes(b"")
                (dist / ".gitignore").write_text("*\n", encoding="utf-8")
            return _FakeCompleted(0)

        exit_code = verify._run_release(tmp_path, env={}, runner=fake_runner)

        assert exit_code == 0
        twine_call = next(argv for argv in calls if argv[:1] == ["twine"])
        checked = twine_call[2:]
        assert any(path.endswith(".whl") for path in checked)
        assert any(path.endswith(".tar.gz") for path in checked)
        assert not any(path.endswith(".gitignore") for path in checked)


class TestSourceHygiene:
    def test_no_shell_true(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "shell=True" not in source

    def test_is_executable(self) -> None:
        mode = SCRIPT_PATH.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_shebang(self) -> None:
        first_line = SCRIPT_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/usr/bin/env python3"


class TestKeyboardInterrupt:
    def test_main_returns_130_on_keyboard_interrupt(
        self, verify: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_interrupt(*args: Any, **kwargs: Any) -> int:
            raise KeyboardInterrupt

        monkeypatch.setattr(verify, "_run_full", raise_interrupt)

        exit_code = verify.main(["full"])

        assert exit_code == 130


class TestParseArgsGuidanceValidation:
    def test_guidance_requires_check_or_update(self, verify: ModuleType) -> None:
        with pytest.raises(SystemExit):
            verify._parse_args(["guidance"])

    def test_guidance_rejects_both_check_and_update(self, verify: ModuleType) -> None:
        with pytest.raises(SystemExit):
            verify._parse_args(["guidance", "--check", "--update"])

    def test_other_profiles_reject_check(self, verify: ModuleType) -> None:
        with pytest.raises(SystemExit):
            verify._parse_args(["full", "--check"])

    def test_other_profiles_reject_update(self, verify: ModuleType) -> None:
        with pytest.raises(SystemExit):
            verify._parse_args(["fast", "--update"])

    def test_guidance_check_parses(self, verify: ModuleType) -> None:
        args = verify._parse_args(["guidance", "--check"])

        assert args.profile == "guidance"
        assert args.check is True
        assert args.update is False

    def test_guidance_update_parses(self, verify: ModuleType) -> None:
        args = verify._parse_args(["guidance", "--update"])

        assert args.profile == "guidance"
        assert args.check is False
        assert args.update is True


class TestGuidanceBlockBuilding:
    """`_build_guidance_block`/`replace_guidance_block`: the pure string-level seams."""

    def test_build_guidance_block_shape(self, verify: ModuleType) -> None:
        block = verify._build_guidance_block("line one\nline two\n", config_path="fake.json")

        assert block.splitlines() == [
            "<!-- konpy:generated-guidance:start -->",
            "<!-- Generated from fake.json by scripts/verify guidance --update. "
            "Do not edit by hand. -->",
            "line one",
            "line two",
            "<!-- konpy:generated-guidance:end -->",
        ]

    def test_replace_guidance_block_preserves_surrounding_bytes(
        self, verify: ModuleType
    ) -> None:
        text = (
            "before\n"
            f"{verify.GUIDANCE_START_MARKER}\nold\n{verify.GUIDANCE_END_MARKER}\n"
            "after\n"
        )

        replaced = verify.replace_guidance_block(
            text, f"{verify.GUIDANCE_START_MARKER}\nnew\n{verify.GUIDANCE_END_MARKER}"
        )

        assert replaced == (
            "before\n"
            f"{verify.GUIDANCE_START_MARKER}\nnew\n{verify.GUIDANCE_END_MARKER}\n"
            "after\n"
        )

    def test_replace_guidance_block_missing_markers_raises(self, verify: ModuleType) -> None:
        with pytest.raises(verify.GuidanceMarkerError, match="missing"):
            verify.replace_guidance_block("no markers here", "new block")

    def test_replace_guidance_block_duplicated_markers_raises(
        self, verify: ModuleType
    ) -> None:
        text = (
            f"{verify.GUIDANCE_START_MARKER}\na\n{verify.GUIDANCE_END_MARKER}\n"
            f"{verify.GUIDANCE_START_MARKER}\nb\n{verify.GUIDANCE_END_MARKER}\n"
        )

        with pytest.raises(verify.GuidanceMarkerError, match="duplicated"):
            verify.replace_guidance_block(text, "new block")


_FAKE_AGENTS_MD = (
    "# Fake AGENTS\n"
    "\n"
    "Human-authored prose above the markers.\n"
    "\n"
    "<!-- konpy:generated-guidance:start -->\n"
    "<!-- konpy:generated-guidance:end -->\n"
    "\n"
    "Human-authored prose below the markers.\n"
)


class TestUpdateAndCheckGuidance:
    """`update_guidance`/`check_guidance` against tmp files, with a stub generator.

    Every test here passes `agents_md_path`/`config_path` explicitly and a
    stub `generator` -- never the real `AGENTS.md` and never a real `konpy
    explain` subprocess.
    """

    def test_update_then_check_roundtrip(self, verify: ModuleType, tmp_path: Path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")
        generator = lambda: "generated line one\ngenerated line two\n"  # noqa: E731

        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=generator,
        )

        assert (
            verify.check_guidance(
                agents_md_path=agents_md,
                repo_root=REPO_ROOT,
                config_path="konpy.strict.json",
                generator=generator,
            )
            is True
        )

    def test_human_text_outside_markers_preserved_byte_for_byte(
        self, verify: ModuleType, tmp_path: Path
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")

        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=lambda: "generated body\n",
        )

        updated = agents_md.read_text(encoding="utf-8")
        assert updated.startswith(
            "# Fake AGENTS\n\nHuman-authored prose above the markers.\n\n"
        )
        assert updated.endswith("\nHuman-authored prose below the markers.\n")

    def test_stale_content_makes_check_fail(self, verify: ModuleType, tmp_path: Path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")
        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=lambda: "stale body\n",
        )

        fresh = verify.check_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=lambda: "current body\n",
        )

        assert fresh is False

    def test_changing_generated_content_makes_check_fail(
        self, verify: ModuleType, tmp_path: Path
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")
        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=lambda: "version one\n",
        )

        assert (
            verify.check_guidance(
                agents_md_path=agents_md,
                repo_root=REPO_ROOT,
                config_path="konpy.strict.json",
                generator=lambda: "version two\n",
            )
            is False
        )

    def test_missing_markers_raises_clear_error(
        self, verify: ModuleType, tmp_path: Path
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# No markers here at all.\n", encoding="utf-8")

        with pytest.raises(verify.GuidanceMarkerError, match="missing"):
            verify.update_guidance(
                agents_md_path=agents_md,
                repo_root=REPO_ROOT,
                config_path="konpy.strict.json",
                generator=lambda: "body\n",
            )

        assert agents_md.read_text(encoding="utf-8") == "# No markers here at all.\n"

    def test_duplicated_markers_raises_clear_error(
        self, verify: ModuleType, tmp_path: Path
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        duplicated = (
            f"{verify.GUIDANCE_START_MARKER}\na\n{verify.GUIDANCE_END_MARKER}\n"
            f"{verify.GUIDANCE_START_MARKER}\nb\n{verify.GUIDANCE_END_MARKER}\n"
        )
        agents_md.write_text(duplicated, encoding="utf-8")

        with pytest.raises(verify.GuidanceMarkerError, match="duplicated"):
            verify.update_guidance(
                agents_md_path=agents_md,
                repo_root=REPO_ROOT,
                config_path="konpy.strict.json",
                generator=lambda: "body\n",
            )

        assert agents_md.read_text(encoding="utf-8") == duplicated


class TestRunGuidance:
    """`_run_guidance`: the `--check`/`--update` CLI-level exit-code contract."""

    def test_check_exits_zero_when_fresh(self, verify: ModuleType, tmp_path: Path) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")
        generator = lambda: "same body\n"  # noqa: E731
        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=generator,
        )

        exit_code = verify._run_guidance(
            REPO_ROOT,
            check=True,
            agents_md_path=agents_md,
            config_path="konpy.strict.json",
            generator=generator,
        )

        assert exit_code == 0

    def test_check_exits_nonzero_with_stale_message_on_mismatch(
        self, verify: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(_FAKE_AGENTS_MD, encoding="utf-8")
        verify.update_guidance(
            agents_md_path=agents_md,
            repo_root=REPO_ROOT,
            config_path="konpy.strict.json",
            generator=lambda: "old body\n",
        )
        before = agents_md.read_text(encoding="utf-8")
        capsys.readouterr()  # drain the update's own stdout line

        exit_code = verify._run_guidance(
            REPO_ROOT,
            check=True,
            agents_md_path=agents_md,
            config_path="konpy.strict.json",
            generator=lambda: "new body\n",
        )

        assert exit_code == 1
        assert agents_md.read_text(encoding="utf-8") == before, "check must write nothing"
        stderr = capsys.readouterr().err.strip()
        assert stderr == (
            "AGENTS.md guidance is stale; run: uv run scripts/verify guidance --update"
        )

    def test_check_exits_nonzero_with_stale_message_on_missing_markers(
        self, verify: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# no markers\n", encoding="utf-8")

        exit_code = verify._run_guidance(
            REPO_ROOT,
            check=True,
            agents_md_path=agents_md,
            config_path="konpy.strict.json",
            generator=lambda: "body\n",
        )

        assert exit_code == 1
        assert agents_md.read_text(encoding="utf-8") == "# no markers\n"
        stderr = capsys.readouterr().err.strip()
        assert stderr == (
            "AGENTS.md guidance is stale; run: uv run scripts/verify guidance --update"
        )

    def test_update_exits_nonzero_with_clear_error_on_missing_markers(
        self, verify: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# no markers\n", encoding="utf-8")

        exit_code = verify._run_guidance(
            REPO_ROOT,
            check=False,
            agents_md_path=agents_md,
            config_path="konpy.strict.json",
            generator=lambda: "body\n",
        )

        assert exit_code == 1
        assert agents_md.read_text(encoding="utf-8") == "# no markers\n"
        stderr = capsys.readouterr().err
        assert "missing" in stderr


class TestGuidanceRealSubprocess:
    """The one real-subprocess guidance test: no stubbing, the actual repo state."""

    def test_check_exits_zero_on_the_actual_repo_after_a_real_update(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "guidance", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
