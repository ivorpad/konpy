from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from konpy.cli.agent_runner import AgentInvocation, AgentRunResult
from konpy.cli.app import _preprocess_argv
from konpy.cli.hook import HookAgent
from konpy.cli.review import run_review_command

SENTINEL_ENV = "KONPY_HOOK_ACTIVE"


def payload_json(
    *,
    tool_name: str | None = "Write",
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = "/project",
    session_id: str | None = "session-1",
) -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input": {} if tool_input is None else tool_input,
            "cwd": cwd,
        }
    )


def prompt_verdict(
    *,
    verdict: str = "pass",
    reasons: list[object] | None = None,
) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "reasons": [] if reasons is None else reasons,
        }
    )


def rules_verdict(
    *,
    verdict: str = "pass",
    failures: list[dict[str, object]] | None = None,
) -> str:
    return json.dumps(
        {
            "verdict": verdict,
            "failures": [] if failures is None else failures,
        }
    )


def default_rules() -> list[dict[str, object]]:
    return [
        {
            "name": "contextual-errors",
            "prompt": "Verify that errors contain useful operation context.",
            "match": ["src/**/*.py"],
            "source": "Errors must contain useful context.",
        },
        {
            "name": "honest-docstrings",
            "prompt": "Verify that docstrings match the implemented behavior.",
            "match": ["src/**/*.py"],
            "source": "Docstrings must not be aspirational.",
        },
    ]


def write_rules(
    path: Path,
    *,
    rules: list[dict[str, object]] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "semanticRulesSpecVersion": "v1",
                "rules": default_rules() if rules is None else rules,
            }
        ),
        encoding="utf-8",
    )


class FakeRunner:
    def __init__(
        self,
        responses: AgentRunResult | str | list[AgentRunResult | str],
    ) -> None:
        self._responses = (
            list(responses) if isinstance(responses, list) else [responses]
        )
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(
        self,
        invocation: AgentInvocation,
        prompt: str,
    ) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def additional_context(stdout: str) -> str:
    """Extract the additionalContext string from a review's stdout JSON."""
    decoded = json.loads(stdout)
    return decoded["hookSpecificOutput"]["additionalContext"]


class TestNeverBlocks:
    def test_source_never_returns_two(self) -> None:
        source = Path("src/konpy/cli/review.py").read_text(encoding="utf-8")
        assert "return 2" not in source

    def test_single_prompt_fail_exits_zero_with_reasons_and_context(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt="Check the implementation.",
            rules_path=None,
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                prompt_verdict(
                    verdict="fail",
                    reasons=["Implementation does not match the docstring."],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Implementation does not match the docstring." in captured.err

        context = additional_context(captured.out)
        assert "konpy review findings:" in context
        assert (
            "src/service.py: Implementation does not match the docstring."
            in context
        )

    def test_rules_fail_exits_zero_with_rule_prefixed_context(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {
                            "rule": "honest-docstrings",
                            "reasons": ["Docstring overstates behavior."],
                        }
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "honest-docstrings: Docstring overstates behavior." in captured.err

        context = additional_context(captured.out)
        assert "src/service.py: honest-docstrings: Docstring overstates behavior." in context


class TestNoStopOnFirstFailure:
    def test_all_paths_verified_and_all_findings_logged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        log_path = tmp_path / "findings.jsonl"
        write_rules(rules_path)
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/a.py\n"
            "@@\n-old\n+new\n"
            "*** Update File: src/b.py\n"
            "@@\n-old\n+new\n"
            "*** End Patch\n"
        )
        runner = FakeRunner(
            [
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "contextual-errors", "reasons": ["first file bad"]}
                    ],
                ),
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {"rule": "honest-docstrings", "reasons": ["second file bad"]}
                    ],
                ),
            ]
        )

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CODEX,
            log_path=str(log_path),
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": patch},
            ),
            runner=runner,
            env={},
        )

        captured = capsys.readouterr()
        records = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
        ]

        assert exit_code == 0
        assert len(runner.calls) == 2
        assert len(records) == 2
        assert records[0]["filePath"] == "src/a.py"
        assert records[1]["filePath"] == "src/b.py"

        context = additional_context(captured.out)
        assert "src/a.py: contextual-errors: first file bad" in context
        assert "src/b.py: honest-docstrings: second file bad" in context


class TestAgentUnavailableIsAdvisory:
    def test_agent_not_on_path_warns_and_exits_zero(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda _binary: None,
        )

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "not found on PATH" in captured.err
        assert captured.out == ""

    def test_invalid_verdict_warns_and_exits_zero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner("not a verdict"),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "did not return a valid verdict" in captured.err
        assert captured.out == ""


class TestModeValidation:
    def test_prompt_and_rules_together_exit_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt="Check it.",
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=None,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "--prompt and --rules are mutually exclusive" in captured.err

    def test_neither_prompt_nor_rules_exits_one(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=None,
            agent=HookAgent.CLAUDE,
            stdin_text=None,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert (
            "Exactly one of --prompt or --rules is required for konpy review."
            in captured.err
        )

    def test_invalid_agent_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent="auto",
            stdin_text="",
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Invalid agent" in captured.err


class TestCliWiring:
    def test_review_argv_is_recognized_as_a_subcommand_not_rerouted_to_check(
        self,
    ) -> None:
        argv = ["review", "--prompt", "x"]
        assert _preprocess_argv(argv) == argv


class TestSentinelAndSkips:
    def test_recursion_sentinel_skips(self) -> None:
        exit_code = run_review_command(
            match=[],
            prompt=None,
            rules_path=None,
            agent=None,
            stdin_text=None,
            env={SENTINEL_ENV: "1"},
        )

        assert exit_code == 0

    def test_pass_produces_no_stdout(self, tmp_path: Path) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(rules_verdict()),
            env={},
        )

        assert exit_code == 0

    def test_non_write_tool_skips_without_agent(self, tmp_path: Path) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_review_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_name="Bash",
                tool_input={"command": "ls"},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert runner.calls == []
