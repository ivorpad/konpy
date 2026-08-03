from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from konpy.cli._hook_findings import HookFinding
from konpy.cli._hook_prompt_run import run_prompt_verifications
from konpy.cli._hook_rules_run import run_rules_verifications
from konpy.cli._hook_support import HookPayload
from konpy.cli._review_outcome import combined_review_status
from konpy.cli._semantic_rules import SemanticRuleV1
from konpy.cli.agent_runner import AgentInvocation, AgentRunResult
from konpy.config.errors import Err, Ok, Result

INVOCATION = AgentInvocation(agent="claude", executable="/bin/claude", prefix_args=())


def payload() -> HookPayload:
    return HookPayload.model_validate(
        {
            "session_id": "session-1",
            "tool_name": "Write",
            "tool_input": {},
            "cwd": "/project",
        }
    )


def prompt_verdict(*, verdict: str = "pass", reasons: list[object] | None = None) -> str:
    return json.dumps({"verdict": verdict, "reasons": [] if reasons is None else reasons})


def rules_verdict(
    *,
    verdict: str = "pass",
    failures: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps({"verdict": verdict, "failures": [] if failures is None else failures})


def one_rule() -> list[SemanticRuleV1]:
    return [
        SemanticRuleV1.model_validate(
            {
                "name": "contextual-errors",
                "prompt": "Verify that errors contain useful operation context.",
                "match": ["src/**/*.py"],
            }
        )
    ]


class RecordingRunner:
    """Records every prompt it is called with and returns queued responses."""

    def __init__(self, responses: list[AgentRunResult | str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> AgentRunResult:
        self.calls.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, AgentRunResult):
            return response
        return AgentRunResult(returncode=0, stdout=response, stderr="")


def noop_write_error(_message: str) -> None:
    return None


def recording_append_finding(
    log: list[HookFinding],
) -> Callable[[str | Path, HookFinding], Result[None]]:
    def _append(_path: str | Path, finding: HookFinding) -> Result[None]:
        log.append(finding)
        return Ok(None)

    return _append


class TestCombinedReviewStatus:
    def test_findings_take_priority_over_everything(self) -> None:
        assert (
            combined_review_status(
                has_findings=True,
                saw_invalid_response=True,
                saw_unavailable=True,
            )
            == "findings"
        )

    def test_invalid_response_takes_priority_over_unavailable(self) -> None:
        assert (
            combined_review_status(
                has_findings=False,
                saw_invalid_response=True,
                saw_unavailable=True,
            )
            == "invalid-response"
        )

    def test_unavailable_when_only_agent_run_failures_seen(self) -> None:
        assert (
            combined_review_status(
                has_findings=False,
                saw_invalid_response=False,
                saw_unavailable=True,
            )
            == "unavailable"
        )

    def test_pass_when_nothing_observed(self) -> None:
        assert (
            combined_review_status(
                has_findings=False,
                saw_invalid_response=False,
                saw_unavailable=False,
            )
            == "pass"
        )


class TestPromptVerificationsNonStopMode:
    def test_processes_all_paths_and_logs_every_finding(self, tmp_path: Path) -> None:
        log_path = tmp_path / "findings.jsonl"
        runner = RecordingRunner(
            [
                prompt_verdict(verdict="fail", reasons=["first failed"]),
                prompt_verdict(verdict="fail", reasons=["second failed"]),
            ]
        )
        logged: list[HookFinding] = []

        outcome = run_prompt_verifications(
            paths=["src/a.py", "src/b.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=str(log_path),
            run_verifier=runner,
            append_finding=recording_append_finding(logged),
            write_error=noop_write_error,
            stop_on_first_failure=False,
            command_name="hook",
        )

        assert len(runner.calls) == 2
        assert outcome.status == "findings"
        assert [finding.path for finding in outcome.findings] == [
            "src/a.py",
            "src/b.py",
        ]
        assert len(logged) == 2
        assert logged[0].filePath == "src/a.py"
        assert logged[1].filePath == "src/b.py"

    def test_agent_run_failures_become_warnings_and_processing_continues(
        self,
    ) -> None:
        runner = RecordingRunner(
            [
                AgentRunResult(returncode=1, stdout="", stderr="boom"),
                prompt_verdict(),
            ]
        )

        outcome = run_prompt_verifications(
            paths=["src/a.py", "src/b.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=None,
            run_verifier=runner,
            append_finding=lambda _path, _finding: Ok(None),
            write_error=noop_write_error,
            stop_on_first_failure=False,
            command_name="hook",
        )

        assert len(runner.calls) == 2
        assert outcome.status == "unavailable"
        assert outcome.findings == ()
        assert len(outcome.warnings) == 1

    def test_invalid_verdict_outranks_unavailable_across_paths(self) -> None:
        runner = RecordingRunner(
            [
                AgentRunResult(returncode=1, stdout="", stderr="boom"),
                "not json",
            ]
        )

        outcome = run_prompt_verifications(
            paths=["src/a.py", "src/b.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=None,
            run_verifier=runner,
            append_finding=lambda _path, _finding: Ok(None),
            write_error=noop_write_error,
            stop_on_first_failure=False,
            command_name="hook",
        )

        assert len(runner.calls) == 2
        assert outcome.status == "invalid-response"
        assert len(outcome.warnings) == 2


class TestPromptVerificationsStopMode:
    def test_stops_at_first_failing_path(self) -> None:
        runner = RecordingRunner(
            [
                prompt_verdict(verdict="fail", reasons=["first failed"]),
                prompt_verdict(verdict="fail", reasons=["second failed"]),
            ]
        )

        outcome = run_prompt_verifications(
            paths=["src/a.py", "src/b.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=None,
            run_verifier=runner,
            append_finding=lambda _path, _finding: Ok(None),
            write_error=noop_write_error,
            stop_on_first_failure=True,
            command_name="hook",
        )

        assert len(runner.calls) == 1
        assert outcome.status == "findings"
        assert [finding.path for finding in outcome.findings] == ["src/a.py"]

    def test_stops_at_first_agent_run_failure(self) -> None:
        runner = RecordingRunner(
            [
                AgentRunResult(returncode=1, stdout="", stderr="boom"),
                prompt_verdict(),
            ]
        )

        outcome = run_prompt_verifications(
            paths=["src/a.py", "src/b.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=None,
            run_verifier=runner,
            append_finding=lambda _path, _finding: Ok(None),
            write_error=noop_write_error,
            stop_on_first_failure=True,
            command_name="hook",
        )

        assert len(runner.calls) == 1
        assert outcome.status == "unavailable"


class TestRulesVerificationsNonStopMode:
    def test_processes_all_batches_and_logs_every_finding(
        self,
        tmp_path: Path,
    ) -> None:
        log_path = tmp_path / "findings.jsonl"
        runner = RecordingRunner(
            [
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "contextual-errors", "reasons": ["first failed"]}
                    ],
                ),
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "contextual-errors", "reasons": ["second failed"]}
                    ],
                ),
            ]
        )
        logged: list[HookFinding] = []

        outcome = run_rules_verifications(
            batches=[("src/a.py", one_rule()), ("src/b.py", one_rule())],
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=str(log_path),
            run_verifier=runner,
            append_finding=recording_append_finding(logged),
            write_error=noop_write_error,
            stop_on_first_failure=False,
            command_name="hook",
        )

        assert len(runner.calls) == 2
        assert outcome.status == "findings"
        assert [finding.path for finding in outcome.findings] == [
            "src/a.py",
            "src/b.py",
        ]
        assert len(logged) == 2
        assert logged[0].filePath == "src/a.py"
        assert logged[1].filePath == "src/b.py"


class TestRulesVerificationsStopMode:
    def test_stops_at_first_failing_batch(self) -> None:
        runner = RecordingRunner(
            [
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "contextual-errors", "reasons": ["first failed"]}
                    ],
                ),
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "contextual-errors", "reasons": ["second failed"]}
                    ],
                ),
            ]
        )

        outcome = run_rules_verifications(
            batches=[("src/a.py", one_rule()), ("src/b.py", one_rule())],
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=None,
            run_verifier=runner,
            append_finding=lambda _path, _finding: Ok(None),
            write_error=noop_write_error,
            stop_on_first_failure=True,
            command_name="hook",
        )

        assert len(runner.calls) == 1
        assert outcome.status == "findings"
        assert [finding.path for finding in outcome.findings] == ["src/a.py"]


class TestLogWriteFailureWarningNamesCallingCommand:
    """A `--log` append failure must name whichever command is actually
    running (`konpy hook` or `konpy review`), not a hardcoded literal --
    `run_prompt_verifications`/`run_rules_verifications` are shared plumbing
    for both commands."""

    def test_prompt_mode_warning_names_the_calling_command(self, tmp_path: Path) -> None:
        errors: list[str] = []
        runner = RecordingRunner([prompt_verdict(verdict="fail", reasons=["broke"])])

        run_prompt_verifications(
            paths=["src/a.py"],
            prompt="Check it.",
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=str(tmp_path / "findings.jsonl"),
            run_verifier=runner,
            append_finding=lambda _path, _finding: Err("disk full"),
            write_error=errors.append,
            stop_on_first_failure=False,
            command_name="review",
        )

        assert "konpy review: --log warning: disk full" in errors

    def test_rules_mode_warning_names_the_calling_command(self, tmp_path: Path) -> None:
        errors: list[str] = []
        runner = RecordingRunner(
            [
                rules_verdict(
                    verdict="fail",
                    failures=[{"rule": "contextual-errors", "reasons": ["broke"]}],
                )
            ]
        )

        run_rules_verifications(
            batches=[("src/a.py", one_rule())],
            payload=payload(),
            invocation=INVOCATION,
            agent_value="claude",
            model="sonnet",
            log_path=str(tmp_path / "findings.jsonl"),
            run_verifier=runner,
            append_finding=lambda _path, _finding: Err("disk full"),
            write_error=errors.append,
            stop_on_first_failure=False,
            command_name="hook",
        )

        assert "konpy hook: --log warning: disk full" in errors
