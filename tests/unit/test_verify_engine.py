from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from konpy.config.errors import Ok
from konpy.config.loader import load_config
from konpy.config.schema import RawConfigV1
from konpy.core.verify import (
    VerifyStep,
    VerifyStepResult,
    execute_step,
    run_verify_steps,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class _FakeCompleted:
    """Minimal stand-in for `subprocess.CompletedProcess` in fake runners."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class TestExecuteStep:
    def test_ok_step_reports_ok_with_no_message(self) -> None:
        step = VerifyStep("pytest", ("true",))

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(0)

        result = execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result == VerifyStepResult(
            name="pytest", ok=True, duration=result.duration, message=None
        )
        assert result.duration >= 0

    def test_nonzero_exit_reports_failure_with_exit_code_message(self) -> None:
        step = VerifyStep("ruff", ("false",))

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(3)

        result = execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result.ok is False
        assert result.message == "exit code 3"

    def test_missing_executable_is_a_failure_not_an_exception(self) -> None:
        step = VerifyStep("missing-tool", ("does-not-exist",))

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            raise FileNotFoundError("does-not-exist")

        result = execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result.ok is False
        assert result.message is not None
        assert "executable not found" in result.message

    def test_timeout_is_a_failure_naming_the_configured_seconds(self) -> None:
        step = VerifyStep("slow", ("sleep", "10"), timeout=5)

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=5)

        result = execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result.ok is False
        assert result.message == "timed out after 5s"

    def test_step_name_is_carried_onto_the_result(self) -> None:
        step = VerifyStep("named-step", ("true",))

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(0)

        result = execute_step(step, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert result.name == "named-step"


class TestRunVerifySteps:
    def test_every_step_runs_even_after_an_earlier_failure(self) -> None:
        steps = [
            VerifyStep("one", ("true",)),
            VerifyStep("two", ("false",)),
            VerifyStep("three", ("true",)),
            VerifyStep("four", ("false",)),
        ]
        returncodes = {"one": 0, "two": 1, "three": 0, "four": 1}

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            name = next(step.name for step in steps if list(step.argv) == argv)
            return _FakeCompleted(returncodes[name])

        results = run_verify_steps(steps, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert [result.name for result in results] == ["one", "two", "three", "four"]
        assert [result.ok for result in results] == [True, False, True, False]

    def test_on_result_streams_each_result_immediately_in_order(self) -> None:
        steps = [
            VerifyStep("one", ("true",)),
            VerifyStep("two", ("false",)),
        ]
        returncodes = {"one": 0, "two": 1}
        streamed: list[VerifyStepResult] = []

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            name = next(step.name for step in steps if list(step.argv) == argv)
            return _FakeCompleted(returncodes[name])

        results = run_verify_steps(
            steps, cwd=REPO_ROOT, env={}, runner=fake_runner, on_result=streamed.append
        )

        assert streamed == results
        assert [result.name for result in streamed] == ["one", "two"]

    def test_on_result_is_optional(self) -> None:
        steps = [VerifyStep("one", ("true",))]

        def fake_runner(argv: list[str], **kwargs: Any) -> _FakeCompleted:
            return _FakeCompleted(0)

        results = run_verify_steps(steps, cwd=REPO_ROOT, env={}, runner=fake_runner)

        assert len(results) == 1

    def test_empty_roster_returns_no_results(self) -> None:
        results = run_verify_steps([], cwd=REPO_ROOT, env={}, runner=lambda *a, **k: None)

        assert results == []


def _config(steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"version": "v1", "conventions": []}
    if steps is not None:
        payload["verify"] = {"steps": steps}
    return payload


class TestVerifyConfigSchema:
    def test_verify_section_is_accepted(self) -> None:
        config = RawConfigV1.model_validate(
            _config([{"name": "ruff", "run": ["ruff", "check"]}])
        )

        assert config.verify is not None
        assert config.verify.steps[0].name == "ruff"
        assert config.verify.steps[0].run == ["ruff", "check"]
        assert config.verify.steps[0].timeout == 1800

    def test_verify_section_is_optional(self) -> None:
        config = RawConfigV1.model_validate(_config())

        assert config.verify is None

    def test_custom_timeout_is_honored(self) -> None:
        config = RawConfigV1.model_validate(
            _config([{"name": "pytest", "run": ["pytest"], "timeout": 60}])
        )

        assert config.verify is not None
        assert config.verify.steps[0].timeout == 60

    def test_duplicate_step_names_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate verify step name"):
            RawConfigV1.model_validate(
                _config(
                    [
                        {"name": "ruff", "run": ["ruff", "check"]},
                        {"name": "ruff", "run": ["ruff", "format", "--check"]},
                    ]
                )
            )

    def test_empty_steps_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawConfigV1.model_validate(_config([]))

    def test_empty_run_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawConfigV1.model_validate(_config([{"name": "ruff", "run": []}]))

    def test_empty_step_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawConfigV1.model_validate(_config([{"name": "", "run": ["ruff"]}]))

    def test_zero_timeout_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawConfigV1.model_validate(
                _config([{"name": "ruff", "run": ["ruff"], "timeout": 0}])
            )

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawConfigV1.model_validate(
                {
                    "version": "v1",
                    "conventions": [],
                    "verify": {"steps": [{"name": "ruff", "run": ["ruff"]}], "parallel": True},
                }
            )


class TestVerifyExtendsReplacement:
    """Pins `verify`'s inheritance semantics: wholesale replacement, not per-step merge."""

    def test_child_verify_replaces_parent_verify_wholesale(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        _write_json(
            parent_path,
            {
                "version": "v1",
                "conventions": [],
                "verify": {
                    "steps": [
                        {"name": "parent-ruff", "run": ["ruff", "check"]},
                        {"name": "parent-pytest", "run": ["pytest"]},
                    ]
                },
            },
        )
        config_path = tmp_path / "konpy.json"
        _write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
                "verify": {"steps": [{"name": "child-pytest", "run": ["pytest", "-q"]}]},
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.verify is not None
        assert [step.name for step in result.value.verify.steps] == ["child-pytest"]
        assert result.value.verify.steps[0].run == ["pytest", "-q"]

    def test_parent_verify_is_inherited_when_child_declares_none(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        _write_json(
            parent_path,
            {
                "version": "v1",
                "conventions": [],
                "verify": {"steps": [{"name": "parent-ruff", "run": ["ruff", "check"]}]},
            },
        )
        config_path = tmp_path / "konpy.json"
        _write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.verify is not None
        assert [step.name for step in result.value.verify.steps] == ["parent-ruff"]

    def test_child_with_no_verify_and_no_parent_verify_stays_none(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        _write_json(parent_path, {"version": "v1", "conventions": []})
        config_path = tmp_path / "konpy.json"
        _write_json(
            config_path,
            {"version": "v1", "extends": ["./base.json"], "conventions": []},
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.verify is None
