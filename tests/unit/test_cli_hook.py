from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from konpy.cli.agent_runner import AgentInvocation, AgentRunResult
from konpy.cli.app import _preprocess_argv, app
from konpy.cli.hook import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOLS,
    DEFAULT_TIMEOUT,
    SENTINEL_ENV,
    HookAgent,
    build_hook_prompt,
    build_rules_hook_prompt,
    extract_target_paths,
    hook_child_args,
    parse_rules_verdict,
    parse_verdict,
    path_matches_any,
    run_hook_command,
)
from konpy.config.errors import Err

cli_runner = CliRunner()


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


def semantic_package(
    *,
    rules: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "semanticRulesSpecVersion": "v1",
        "rules": default_rules() if rules is None else rules,
    }


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
        {
            "name": "focused-tests",
            "prompt": "Verify that each test has one clear behavioral purpose.",
            "match": ["tests/**/*.py"],
            "source": "Tests must have one clear purpose.",
        },
    ]


def write_rules(
    path: Path,
    *,
    rules: list[dict[str, object]] | None = None,
) -> None:
    path.write_text(
        json.dumps(semantic_package(rules=rules)),
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


class TestModeValidation:
    def test_neither_prompt_nor_rules_exits_one_before_stdin(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = run_hook_command(
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
            "Exactly one of --prompt or --rules is required for konpy hook."
            in captured.err
        )

    def test_prompt_and_rules_together_exit_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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

    def test_missing_or_invalid_agent_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        missing_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=None,
            stdin_text="",
            env={},
        )
        missing_error = capsys.readouterr().err

        invalid_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent="auto",
            stdin_text="",
            env={},
        )
        invalid_error = capsys.readouterr().err

        assert missing_code == 1
        assert "--agent" in missing_error
        assert invalid_code == 1
        assert "Invalid agent" in invalid_error

    def test_recursion_sentinel_skips_before_mode_validation(self) -> None:
        exit_code = run_hook_command(
            match=[],
            prompt=None,
            rules_path=None,
            agent=None,
            stdin_text=None,
            env={SENTINEL_ENV: "1"},
        )

        assert exit_code == 0


class TestRulesLoading:
    def test_missing_rules_file_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(tmp_path / "missing.json"),
            agent=HookAgent.CLAUDE,
            stdin_text="",
            runner=FakeRunner(rules_verdict()),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Could not read semantic rules file:" in captured.err

    def test_malformed_rules_file_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        rules_path.write_text('{"rules":', encoding="utf-8")

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text="",
            runner=FakeRunner(rules_verdict()),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Malformed JSON" in captured.err

    def test_invalid_rules_schema_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(
            json.dumps(
                {
                    "semanticRulesSpecVersion": "v1",
                    "rules": [
                        {
                            "name": "missing-prompt",
                            "match": ["**/*.py"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text="",
            runner=FakeRunner(rules_verdict()),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Invalid semantic rules file:" in captured.err
        assert "prompt" in captured.err


class TestPayloadAndPathSkips:
    @pytest.mark.parametrize("stdin_text", ["", "not json", "[]"])
    def test_invalid_payloads_skip_without_agent(
        self,
        tmp_path: Path,
        stdin_text: str,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=stdin_text,
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert runner.calls == []

    def test_non_write_tool_skips_without_agent(self, tmp_path: Path) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
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

    def test_global_match_is_applied_before_rule_match(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["tests/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert runner.calls == []

    def test_no_applicable_rules_skips_before_agent_resolution(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        def fail_if_resolved(_binary: str) -> str | None:
            raise AssertionError("agent resolution must not run")

        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            fail_if_resolved,
        )

        exit_code = run_hook_command(
            match=["docs/**/*.md"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "docs/guide.md"},
            ),
            env={},
        )

        assert exit_code == 0


class TestRulesSelectionAndPrompt:
    def test_selects_only_rules_matching_current_file(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert len(runner.calls) == 1
        prompt = runner.calls[0][1]
        assert 'Rule "contextual-errors"' in prompt
        assert 'Rule "honest-docstrings"' in prompt
        assert 'Rule "focused-tests"' not in prompt

    def test_batch_contains_all_names_and_prompts_but_not_source(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        prompt = runner.calls[0][1]
        assert "Verify that errors contain useful operation context." in prompt
        assert "Verify that docstrings match the implemented behavior." in prompt
        assert "Errors must contain useful context." not in prompt
        assert "Docstrings must not be aspirational." not in prompt
        assert '"failures"' in prompt
        assert "Only rule names listed above are valid." in prompt
        assert "read-only" in prompt.lower()

    def test_multiple_rules_for_one_file_use_one_agent_call(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert len(runner.calls) == 1

    def test_one_batch_is_run_per_applicable_file(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
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
                rules_verdict(),
                rules_verdict(),
            ]
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": patch},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert len(runner.calls) == 2
        assert "src/a.py" in runner.calls[0][1]
        assert "src/b.py" in runner.calls[1][1]

    def test_duplicate_paths_in_patch_are_verified_once_in_rules_mode(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/a.py\n"
            "@@\n-old\n+new\n"
            "*** Update File: src/a.py\n"
            "@@\n-old-again\n+new-again\n"
            "*** End Patch\n"
        )
        runner = FakeRunner(rules_verdict())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": patch},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 0
        assert len(runner.calls) == 1


class TestRulesVerdicts:
    def test_pass_exits_zero(self, tmp_path: Path) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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

    def test_per_rule_fail_exits_two_with_prefixed_feedback(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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
                            "reasons": [
                                "The docstring claims persistence but only validates."
                            ],
                        }
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert (
            "honest-docstrings: The docstring claims persistence but only validates."
            in captured.err
        )
        assert captured.out == ""

    def test_fail_with_no_failures_synthesizes_first_rule_reason(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(rules_verdict(verdict="fail", failures=[])),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert (
            "contextual-errors: Verification failed for src/service.py "
            "without a rule-specific reason."
        ) in captured.err

    def test_named_failure_with_empty_reasons_is_synthesized(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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
                            "reasons": [],
                        }
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert (
            "honest-docstrings: Verification failed for src/service.py "
            "without a rule-specific reason."
        ) in captured.err

    def test_duplicate_and_out_of_order_failures_are_normalized(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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
                            "reasons": ["doc reason", "doc reason"],
                        },
                        {
                            "rule": "contextual-errors",
                            "reasons": ["error reason"],
                        },
                        {
                            "rule": "honest-docstrings",
                            "reasons": ["second doc reason"],
                        },
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.err.count("honest-docstrings: doc reason") == 1
        assert captured.err.count("honest-docstrings: second doc reason") == 1
        assert captured.err.index("contextual-errors:") < captured.err.index(
            "honest-docstrings:"
        )

    def test_unknown_rule_name_is_infra_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
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
                            "rule": "invented-rule",
                            "reasons": ["bad"],
                        }
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "unknown or inapplicable rule" in captured.err

    def test_pass_with_failures_is_infra_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                rules_verdict(
                    verdict="pass",
                    failures=[
                        {
                            "rule": "contextual-errors",
                            "reasons": ["contradiction"],
                        }
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert 'A "pass" rules verdict must have no failures.' in captured.err

    def test_unparseable_or_malformed_rules_verdict_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        for response in (
            "not json",
            json.dumps({"verdict": "fail", "failures": "wrong"}),
            json.dumps(
                {
                    "verdict": "fail",
                    "failures": [{"rule": 12, "reasons": []}],
                }
            ),
        ):
            exit_code = run_hook_command(
                match=["src/**/*.py"],
                prompt=None,
                rules_path=str(rules_path),
                agent=HookAgent.CLAUDE,
                stdin_text=payload_json(
                    tool_input={"file_path": "src/service.py"},
                ),
                runner=FakeRunner(response),
                env={},
            )
            assert exit_code == 1

        assert "did not return a valid verdict" in capsys.readouterr().err


class TestRulesFindingLog:
    def test_one_finding_per_failed_rule_uses_rule_specific_prompt(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        log_path = tmp_path / "findings.jsonl"
        write_rules(rules_path)

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            model="opus",
            log_path=str(log_path),
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {
                            "rule": "contextual-errors",
                            "reasons": ["Missing operation name."],
                        },
                        {
                            "rule": "honest-docstrings",
                            "reasons": ["Docstring overstates behavior."],
                        },
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        records = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
        ]
        assert exit_code == 2
        assert len(records) == 2
        assert records[0]["rule"] == "contextual-errors"
        assert (
            records[0]["prompt"]
            == "Verify that errors contain useful operation context."
        )
        assert records[0]["reasons"] == ["Missing operation name."]
        assert records[1]["rule"] == "honest-docstrings"
        assert (
            records[1]["prompt"]
            == "Verify that docstrings match the implemented behavior."
        )
        assert records[1]["reasons"] == ["Docstring overstates behavior."]
        assert records[0]["filePath"] == "src/service.py"
        assert records[0]["sessionId"] == "session-1"
        assert records[0]["model"] == "opus"
        assert captured.err.index("contextual-errors:") < captured.err.index(
            "honest-docstrings:"
        )

    def test_each_failed_rule_log_append_is_attempted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        attempted: list[str | None] = []

        def failing_append(_path, finding):
            attempted.append(finding.rule)
            return Err(f"failed {finding.rule}")

        monkeypatch.setattr(
            "konpy.cli.hook.append_hook_finding",
            failing_append,
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            log_path="findings.jsonl",
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                rules_verdict(
                    verdict="fail",
                    failures=[
                        {
                            "rule": "contextual-errors",
                            "reasons": ["first"],
                        },
                        {
                            "rule": "honest-docstrings",
                            "reasons": ["second"],
                        },
                    ],
                )
            ),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert attempted == ["contextual-errors", "honest-docstrings"]
        assert captured.err.index("second") < captured.err.index("--log warning")
        assert "failed contextual-errors" in captured.err
        assert "failed honest-docstrings" in captured.err

    def test_pass_does_not_create_log(self, tmp_path: Path) -> None:
        rules_path = tmp_path / "rules.json"
        log_path = tmp_path / "findings.jsonl"
        write_rules(rules_path)

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            log_path=str(log_path),
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(rules_verdict()),
            env={},
        )

        assert exit_code == 0
        assert not log_path.exists()


class TestSinglePromptCompatibility:
    def test_pass_and_fail_behavior_is_preserved(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pass_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="Check the implementation.",
            rules_path=None,
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(prompt_verdict()),
            env={},
        )
        capsys.readouterr()

        fail_code = run_hook_command(
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

        assert pass_code == 0
        assert fail_code == 2
        assert "Implementation does not match the docstring." in captured.err
        assert "honest-docstrings:" not in captured.err

    def test_single_prompt_finding_omits_rule_field(
        self,
        tmp_path: Path,
    ) -> None:
        log_path = tmp_path / "findings.jsonl"

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="Check the implementation.",
            rules_path=None,
            agent=HookAgent.CLAUDE,
            log_path=str(log_path),
            stdin_text=payload_json(
                tool_input={"file_path": "src/service.py"},
            ),
            runner=FakeRunner(
                prompt_verdict(
                    verdict="fail",
                    reasons=["Failure."],
                )
            ),
            env={},
        )

        record = json.loads(log_path.read_text(encoding="utf-8"))
        assert exit_code == 2
        assert record["prompt"] == "Check the implementation."
        assert "rule" not in record

    def test_single_prompt_still_verifies_each_path_until_failure(self) -> None:
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
                prompt_verdict(),
                prompt_verdict(verdict="fail", reasons=["second failed"]),
            ]
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="Check it.",
            rules_path=None,
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": patch},
            ),
            runner=runner,
            env={},
        )

        assert exit_code == 2
        assert len(runner.calls) == 2


class TestPromptAndVerdictHelpers:
    def test_build_single_prompt_contract_is_unchanged(self) -> None:
        prompt = build_hook_prompt(
            file_path="src/x.py",
            cwd="/project",
            user_prompt="Verify the implementation.",
        )

        assert "src/x.py" in prompt
        assert "/project" in prompt
        assert "Verify the implementation." in prompt
        assert '"verdict": "pass" | "fail"' in prompt
        assert '"reasons"' in prompt

    def test_build_rules_prompt_lists_package_order(self) -> None:
        from konpy.cli._semantic_rules import SemanticRuleV1

        rules = [SemanticRuleV1.model_validate(item) for item in default_rules()[:2]]

        prompt = build_rules_hook_prompt(
            file_path="src/x.py",
            cwd="/project",
            rules=rules,
        )

        assert prompt.index('Rule "contextual-errors"') < prompt.index(
            'Rule "honest-docstrings"'
        )
        assert '"failures"' in prompt

    def test_parse_rules_verdict_skips_incidental_json(self) -> None:
        stdout = (
            '{"path": "src/x.py"}\n'
            + rules_verdict(
                verdict="fail",
                failures=[
                    {
                        "rule": "contextual-errors",
                        "reasons": [1, True],
                    }
                ],
            )
        )

        assert parse_rules_verdict(stdout) == {
            "verdict": "fail",
            "failures": [
                {
                    "rule": "contextual-errors",
                    "reasons": ["1", "True"],
                }
            ],
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {"verdict": "maybe", "failures": []},
            {"verdict": "pass", "failures": "wrong"},
            {"verdict": "fail", "failures": [12]},
            {"verdict": "fail", "failures": [{"rule": 12}]},
            {
                "verdict": "fail",
                "failures": [{"rule": "name", "reasons": "wrong"}],
            },
        ],
    )
    def test_parse_rules_verdict_rejects_invalid_shapes(
        self,
        payload: dict[str, object],
    ) -> None:
        assert parse_rules_verdict(json.dumps(payload)) is None

    def test_parse_rules_verdict_defaults_null_failures_and_reasons(self) -> None:
        assert parse_rules_verdict(
            json.dumps({"verdict": "pass", "failures": None})
        ) == {"verdict": "pass", "failures": []}
        assert parse_rules_verdict(
            json.dumps(
                {
                    "verdict": "fail",
                    "failures": [{"rule": "name", "reasons": None}],
                }
            )
        ) == {
            "verdict": "fail",
            "failures": [{"rule": "name", "reasons": []}],
        }

    def test_existing_parse_verdict_behavior_is_preserved(self) -> None:
        stdout = (
            '{"path": "src/x.py"}\n'
            '{"verdict": "fail", "reasons": [1, true]}'
        )

        assert parse_verdict(stdout) == {
            "verdict": "fail",
            "reasons": ["1", "True"],
        }


class TestPathAndChildHelpers:
    def test_write_tool_sets_are_unchanged(self) -> None:
        assert {"Write", "Edit", "MultiEdit"} == CLAUDE_WRITE_TOOLS
        assert {"apply_patch"} == CODEX_WRITE_TOOLS
        assert DEFAULT_TIMEOUT == 300.0

    def test_extracts_claude_and_codex_paths(self) -> None:
        from konpy.cli.hook import HookPayload

        claude_payload = HookPayload.model_validate(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/project/src/x.py"},
                "cwd": "/project",
            }
        )
        codex_payload = HookPayload.model_validate(
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "input": (
                        "*** Begin Patch\n"
                        "*** Update File: src/a.py\n"
                        "*** Update File: src/b.py\n"
                        "*** End Patch\n"
                    )
                },
            }
        )

        assert extract_target_paths(claude_payload) == ["src/x.py"]
        assert extract_target_paths(codex_payload) == ["src/a.py", "src/b.py"]

    def test_path_matching_supports_globstar_and_braces(self) -> None:
        assert path_matches_any("src/deep/a.py", ["src/**/*.py"])
        assert path_matches_any("src/a.py", ["src/{a,b}.py"])
        assert not path_matches_any("docs/a.md", ["src/**/*.py"])
        assert not path_matches_any("src/a.py", [])

    def test_read_only_child_arguments_are_unchanged(self) -> None:
        assert hook_child_args(HookAgent.CLAUDE) == (
            "--allowedTools",
            "Read",
            "Grep",
            "Glob",
            "--settings",
            '{"hooks":{}}',
        )
        assert hook_child_args(HookAgent.CODEX) == ("--sandbox", "read-only")


class TestInfrastructureFailures:
    def test_nonzero_agent_and_invalid_output_exit_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        nonzero_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/x.py"},
            ),
            runner=FakeRunner(
                AgentRunResult(
                    returncode=124,
                    stdout="",
                    stderr="timed out",
                    timed_out=True,
                )
            ),
            env={},
        )
        nonzero_error = capsys.readouterr().err

        invalid_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_input={"file_path": "src/x.py"},
            ),
            runner=FakeRunner("no verdict"),
            env={},
        )
        invalid_error = capsys.readouterr().err

        assert nonzero_code == 1
        assert "timed out" in nonzero_error
        assert invalid_code == 1
        assert "did not return a valid verdict" in invalid_error

    def test_subprocess_receives_sentinel_read_only_args_model_and_timeout(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/{binary}",
        )
        captured: dict[str, object] = {}

        def fake_run_agent_subprocess(**kwargs):
            captured.update(kwargs)
            return AgentRunResult(
                returncode=0,
                stdout=rules_verdict(),
                stderr="",
            )

        monkeypatch.setattr(
            "konpy.cli.hook.run_agent_subprocess",
            fake_run_agent_subprocess,
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            rules_path=str(rules_path),
            agent=HookAgent.CLAUDE,
            model="opus",
            timeout=42.0,
            stdin_text=payload_json(
                tool_input={"file_path": "src/x.py"},
            ),
            env={},
        )

        assert exit_code == 0
        child_env = captured["env"]
        assert isinstance(child_env, dict)
        assert child_env[SENTINEL_ENV] == "1"
        assert captured["extra_args"] == hook_child_args(HookAgent.CLAUDE)
        assert captured["model"] == "opus"
        assert captured["timeout"] == 42.0


class TestCliWiring:
    def test_hook_argv_preprocessing_is_unchanged(self) -> None:
        argv = [
            "hook",
            "--agent",
            "claude",
            "--rules",
            "rules.json",
        ]
        assert _preprocess_argv(argv) == argv

    def test_rules_option_is_accepted_and_skips_on_empty_payload(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        result = cli_runner.invoke(
            app,
            [
                "hook",
                "--agent",
                "claude",
                "--rules",
                str(rules_path),
                "--match",
                "src/**/*.py",
            ],
            input="",
        )

        assert result.exit_code == 0

    def test_prompt_and_rules_cli_combination_exits_one(
        self,
        tmp_path: Path,
    ) -> None:
        rules_path = tmp_path / "rules.json"
        write_rules(rules_path)

        result = cli_runner.invoke(
            app,
            [
                "hook",
                "--agent",
                "claude",
                "--prompt",
                "Check it.",
                "--rules",
                str(rules_path),
            ],
            input="",
        )

        assert result.exit_code == 1
        assert "mutually exclusive" in result.stderr

    def test_neither_mode_cli_exits_one_not_two(self) -> None:
        result = cli_runner.invoke(
            app,
            ["hook", "--agent", "claude"],
            input="",
        )

        assert result.exit_code == 1
        assert result.exit_code != 2
        assert "Exactly one of --prompt or --rules" in result.stderr

    def test_missing_and_invalid_agent_cli_errors_exit_one(self) -> None:
        missing = cli_runner.invoke(
            app,
            ["hook", "--prompt", "Check it."],
            input="",
        )
        invalid = cli_runner.invoke(
            app,
            ["hook", "--agent", "auto", "--prompt", "Check it."],
            input="",
        )

        assert missing.exit_code == 1
        assert "--agent" in missing.stderr
        assert invalid.exit_code == 1
        assert "Invalid agent" in invalid.stderr

    def test_unknown_option_exits_one_not_two(self) -> None:
        result = cli_runner.invoke(
            app,
            [
                "hook",
                "--agent",
                "claude",
                "--prompt",
                "Check it.",
                "--bogus",
                "value",
            ],
            input="{}",
        )

        assert result.exit_code == 1
        assert "--bogus" in result.stderr

    def test_sentinel_cli_skip_remains_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(SENTINEL_ENV, "1")

        result = cli_runner.invoke(app, ["hook"], input="")

        assert result.exit_code == 0
