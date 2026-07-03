from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from konsistent.cli.agent_runner import AgentInvocation, AgentRunResult
from konsistent.cli.app import _preprocess_argv, app
from konsistent.cli.hook import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOLS,
    DEFAULT_TIMEOUT,
    SENTINEL_ENV,
    HookAgent,
    build_hook_prompt,
    extract_target_paths,
    hook_child_args,
    parse_verdict,
    path_matches_any,
    run_hook_command,
)
from konsistent.config.errors import Err

runner = CliRunner()


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


def verdict_response(*, verdict: str = "pass", reasons: list[str] | None = None) -> str:
    return json.dumps({"verdict": verdict, "reasons": [] if reasons is None else reasons})


class FakeRunner:
    def __init__(self, responses: AgentRunResult | str | list[AgentRunResult | str]) -> None:
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(self, invocation: AgentInvocation, prompt: str) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class TestSentinelAndPayloadSkips:
    def test_sentinel_env_short_circuits_before_reading_stdin(self) -> None:
        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=None,
            env={SENTINEL_ENV: "1"},
        )

        assert exit_code == 0

    def test_blank_stdin_exits_zero(self) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text="   ",
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []

    def test_unparseable_json_stdin_exits_zero(self) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text="not { json",
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []

    def test_non_object_json_stdin_exits_zero(self) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text="[1, 2, 3]",
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []

    def test_wrong_tool_exits_zero_and_never_invokes_agent(self) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_name="Bash", tool_input={"command": "ls"}),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []

    def test_non_matching_path_exits_zero_and_never_invokes_agent(self) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "other/file.py"}),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []


class TestClaudeAndCodexToolPaths:
    def test_claude_write_match_and_pass_exits_zero(self) -> None:
        runner_spy = FakeRunner(verdict_response(verdict="pass"))

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_name="Write", tool_input={"file_path": "src/x.py"}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert len(runner_spy.calls) == 1

    def test_claude_edit_fail_exits_two_with_reasons_on_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runner_spy = FakeRunner(
            verdict_response(verdict="fail", reasons=["method body does not match docstring"])
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_name="Edit", tool_input={"file_path": "src/x.py"}
            ),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert "method body does not match docstring" in captured.err
        assert captured.out == ""

    def test_claude_multi_edit_path_extracted_from_top_level_file_path(self) -> None:
        runner_spy = FakeRunner(verdict_response(verdict="pass"))

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(
                tool_name="MultiEdit",
                tool_input={
                    "file_path": "src/x.py",
                    "edits": [{"old_string": "a", "new_string": "b"}],
                },
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert len(runner_spy.calls) == 1
        assert "src/x.py" in runner_spy.calls[0][1]

    def test_codex_apply_patch_envelope_path_is_extracted_and_verified(self) -> None:
        runner_spy = FakeRunner(verdict_response(verdict="pass"))
        patch_text = (
            "*** Begin Patch\n*** Update File: src/x.py\n@@\n-old\n+new\n*** End Patch\n"
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch", tool_input={"input": patch_text}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert len(runner_spy.calls) == 1
        assert "src/x.py" in runner_spy.calls[0][1]

    def test_codex_unified_diff_path_is_extracted_and_verified(self) -> None:
        runner_spy = FakeRunner(verdict_response(verdict="pass"))
        diff_text = "--- a/src/x.py\n+++ b/src/x.py\n@@\n-old\n+new\n"

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch", tool_input={"diff": diff_text}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert len(runner_spy.calls) == 1

    def test_codex_unrecognizable_apply_patch_shape_exits_zero_and_skips_agent(
        self,
    ) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch", tool_input={"unrelated": "value"}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert runner_spy.calls == []

    def test_multiple_matched_paths_are_each_verified_until_first_fail(self) -> None:
        runner_spy = FakeRunner(
            [
                verdict_response(verdict="pass"),
                verdict_response(verdict="fail", reasons=["second file is bad"]),
            ]
        )
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/a.py\n@@\n-old\n+new\n"
            "*** Update File: src/b.py\n@@\n-old\n+new\n"
            "*** End Patch\n"
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch", tool_input={"input": patch_text}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 2
        assert len(runner_spy.calls) == 2

    def test_multiple_matched_paths_short_circuit_on_infra_error(self) -> None:
        runner_spy = FakeRunner(
            [
                verdict_response(verdict="pass"),
                "not valid json at all",
            ]
        )
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/a.py\n@@\n-old\n+new\n"
            "*** Update File: src/b.py\n@@\n-old\n+new\n"
            "*** End Patch\n"
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            stdin_text=payload_json(
                tool_name="apply_patch", tool_input={"input": patch_text}
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 1
        assert len(runner_spy.calls) == 2


class TestInfraFailOpen:
    def test_unparseable_agent_output_exits_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runner_spy = FakeRunner("I refuse to produce JSON.")

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "did not return a valid verdict" in captured.err

    def test_agent_nonzero_exit_exits_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        runner_spy = FakeRunner(
            AgentRunResult(returncode=2, stdout="", stderr="boom")
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert 'exited with code 2' in captured.err
        assert "boom" in captured.err

    def test_agent_timeout_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        runner_spy = FakeRunner(
            AgentRunResult(
                returncode=124,
                stdout="",
                stderr='Agent CLI "claude" timed out after 300.0s.',
                timed_out=True,
            )
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "timed out" in captured.err

    def test_which_missing_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("konsistent.cli.agent_runner.shutil.which", lambda _binary: None)

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "not found on PATH" in captured.err

    def test_invalid_agent_value_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent="not-an-agent",
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Invalid agent" in captured.err

    def test_missing_prompt_exits_one_not_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            agent=HookAgent.CLAUDE,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "--prompt" in captured.err

    def test_missing_agent_exits_one_not_two(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=None,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "--agent" in captured.err

    def test_missing_prompt_and_bad_agent_short_circuit_before_stdin_is_touched(
        self,
    ) -> None:
        runner_spy = FakeRunner(verdict_response())

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt=None,
            agent="bogus",
            stdin_text=None,
            runner=runner_spy,
            env={},
        )

        assert exit_code == 1
        assert runner_spy.calls == []


class TestDefaultSubprocessWiring:
    def test_default_path_spawns_subprocess_with_sentinel_env_and_hook_child_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "konsistent.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/bin/{binary}",
        )
        captured: dict[str, object] = {}

        def fake_run_agent_subprocess(
            *, invocation, prompt, timeout=None, env=None, extra_args=(), model=None
        ):
            captured["env"] = env
            captured["extra_args"] = extra_args
            captured["timeout"] = timeout
            captured["invocation"] = invocation
            captured["model"] = model
            return AgentRunResult(returncode=0, stdout=verdict_response(), stderr="")

        monkeypatch.setattr(
            "konsistent.cli.hook.run_agent_subprocess", fake_run_agent_subprocess
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            timeout=42.0,
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        assert exit_code == 0
        assert captured["env"][SENTINEL_ENV] == "1"
        assert captured["extra_args"] == (
            "--allowedTools",
            "Read",
            "Grep",
            "Glob",
            "--settings",
            '{"hooks":{}}',
        )
        assert captured["timeout"] == 42.0
        assert captured["invocation"].agent == "claude"
        assert captured["model"] == "sonnet"

    def test_custom_model_is_forwarded_to_the_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "konsistent.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/bin/{binary}",
        )
        captured: dict[str, object] = {}

        def fake_run_agent_subprocess(
            *, invocation, prompt, timeout=None, env=None, extra_args=(), model=None
        ):
            captured["model"] = model
            return AgentRunResult(returncode=0, stdout=verdict_response(), stderr="")

        monkeypatch.setattr(
            "konsistent.cli.hook.run_agent_subprocess", fake_run_agent_subprocess
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            model="claude-opus-4-8",
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            env={},
        )

        assert exit_code == 0
        assert captured["model"] == "claude-opus-4-8"


class TestHookChildArgs:
    def test_claude_child_args(self) -> None:
        assert hook_child_args(HookAgent.CLAUDE) == (
            "--allowedTools",
            "Read",
            "Grep",
            "Glob",
            "--settings",
            '{"hooks":{}}',
        )
        assert hook_child_args("claude") == hook_child_args(HookAgent.CLAUDE)

    def test_codex_child_args(self) -> None:
        assert hook_child_args(HookAgent.CODEX) == ("--sandbox", "read-only")
        assert hook_child_args("codex") == hook_child_args(HookAgent.CODEX)


class TestExtractTargetPaths:
    def test_claude_file_path_extracted(self) -> None:
        from konsistent.cli.hook import HookPayload

        payload = HookPayload.model_validate(
            {"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}}
        )

        assert extract_target_paths(payload) == ["src/x.py"]

    def test_claude_missing_file_path_returns_empty(self) -> None:
        from konsistent.cli.hook import HookPayload

        payload = HookPayload.model_validate({"tool_name": "Write", "tool_input": {}})

        assert extract_target_paths(payload) == []

    def test_absolute_claude_path_is_normalized_relative_to_cwd(self) -> None:
        from konsistent.cli.hook import HookPayload

        payload = HookPayload.model_validate(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/project/src/x.py"},
                "cwd": "/project",
            }
        )

        assert extract_target_paths(payload) == ["src/x.py"]

    def test_codex_path_key_takes_precedence_over_scan(self) -> None:
        from konsistent.cli.hook import HookPayload

        payload = HookPayload.model_validate(
            {
                "tool_name": "apply_patch",
                "tool_input": {
                    "file_path": "src/direct.py",
                    "input": "*** Update File: src/scanned.py\n",
                },
            }
        )

        assert extract_target_paths(payload) == ["src/direct.py"]

    def test_non_write_tool_returns_empty(self) -> None:
        from konsistent.cli.hook import HookPayload

        payload = HookPayload.model_validate({"tool_name": "Bash", "tool_input": {}})

        assert extract_target_paths(payload) == []


class TestPathMatchesAny:
    def test_brace_pattern_matches(self) -> None:
        assert path_matches_any("src/a.py", ["src/{a,b}.py"])
        assert path_matches_any("src/b.py", ["src/{a,b}.py"])
        assert not path_matches_any("src/c.py", ["src/{a,b}.py"])

    def test_globstar_pattern_matches_nested_paths(self) -> None:
        assert path_matches_any("src/deep/nested/file.py", ["src/**/*.py"])
        assert not path_matches_any("docs/deep/nested/file.md", ["src/**/*.py"])

    def test_no_patterns_never_matches(self) -> None:
        assert not path_matches_any("src/a.py", [])

    def test_relative_path_matches_relative_pattern(self) -> None:
        assert path_matches_any("src/a.py", ["src/*.py"])

    def test_absolute_style_path_requires_absolute_style_pattern(self) -> None:
        assert path_matches_any("/abs/src/a.py", ["/abs/**/*.py"])
        assert not path_matches_any("/abs/src/a.py", ["src/*.py"])


class TestParseVerdict:
    def test_valid_pass_with_no_reasons(self) -> None:
        assert parse_verdict(json.dumps({"verdict": "pass"})) == {
            "verdict": "pass",
            "reasons": [],
        }

    def test_valid_fail_with_reasons(self) -> None:
        assert parse_verdict(
            json.dumps({"verdict": "fail", "reasons": ["a", "b"]})
        ) == {"verdict": "fail", "reasons": ["a", "b"]}

    def test_fenced_json_is_parsed(self) -> None:
        stdout = "```json\n" + json.dumps({"verdict": "pass", "reasons": []}) + "\n```"
        assert parse_verdict(stdout) == {"verdict": "pass", "reasons": []}

    def test_prose_wrapped_json_is_parsed(self) -> None:
        stdout = "Here you go:\n" + json.dumps({"verdict": "fail", "reasons": ["x"]})
        assert parse_verdict(stdout) == {"verdict": "fail", "reasons": ["x"]}

    def test_invalid_verdict_value_returns_none(self) -> None:
        assert parse_verdict(json.dumps({"verdict": "maybe"})) is None

    def test_missing_verdict_key_returns_none(self) -> None:
        assert parse_verdict(json.dumps({"reasons": []})) is None

    def test_non_list_reasons_returns_none(self) -> None:
        assert parse_verdict(json.dumps({"verdict": "pass", "reasons": "oops"})) is None

    def test_null_reasons_defaults_to_empty_list(self) -> None:
        assert parse_verdict(json.dumps({"verdict": "pass", "reasons": None})) == {
            "verdict": "pass",
            "reasons": [],
        }

    def test_no_json_object_returns_none(self) -> None:
        assert parse_verdict("no json here at all") is None

    def test_incidental_json_before_real_verdict_is_skipped(self) -> None:
        # A verifier agent's transcript may echo an unrelated JSON-shaped
        # snippet (config dump, tool-call echo, example dict) before its
        # final answer. parse_verdict must keep scanning for a candidate
        # that actually looks like a verdict object, not silently return
        # the first JSON-decodable dict and drop the real fail verdict.
        stdout = (
            'Let me check the config first: {"name": "value", "count": 3}\n\n'
            "Based on my review, here is the verdict:\n"
            '{"verdict": "fail", "reasons": ["docstring does not match method body"]}'
        )

        assert parse_verdict(stdout) == {
            "verdict": "fail",
            "reasons": ["docstring does not match method body"],
        }

    def test_incidental_json_in_fenced_block_before_real_verdict_is_skipped(
        self,
    ) -> None:
        stdout = (
            "```json\n"
            '{"path": "src/x.py", "line": 12}\n'
            "```\n"
            "Final answer:\n"
            '{"verdict": "pass", "reasons": []}'
        )

        assert parse_verdict(stdout) == {"verdict": "pass", "reasons": []}

    def test_reasons_values_are_stringified(self) -> None:
        assert parse_verdict(json.dumps({"verdict": "fail", "reasons": [1, True]})) == {
            "verdict": "fail",
            "reasons": ["1", "True"],
        }


class TestBuildHookPrompt:
    def test_prompt_contains_path_cwd_user_prompt_and_verdict_contract(self) -> None:
        prompt = build_hook_prompt(
            file_path="src/x.py",
            cwd="/project",
            user_prompt="Verify each method matches its docstring.",
        )

        assert "src/x.py" in prompt
        assert "/project" in prompt
        assert "Verify each method matches its docstring." in prompt
        assert '"verdict": "pass" | "fail"' in prompt
        assert "read-only" in prompt.lower()
        assert "reasons" in prompt


class TestConstants:
    def test_write_tool_sets(self) -> None:
        assert {"Write", "Edit", "MultiEdit"} == CLAUDE_WRITE_TOOLS
        assert {"apply_patch"} == CODEX_WRITE_TOOLS

    def test_default_timeout(self) -> None:
        assert DEFAULT_TIMEOUT == 300.0


class TestCliWiring:
    def test_hook_is_routed_unchanged_by_preprocess_argv(self) -> None:
        argv = ["hook", "--agent", "claude", "--prompt", "check it"]
        assert _preprocess_argv(argv) == argv

    def test_agent_is_required(self) -> None:
        result = runner.invoke(app, ["hook", "--prompt", "check it"], input="")

        # Missing --agent must fail open (exit 1), never collide with the
        # exit code (2) reserved exclusively for a verified fail verdict.
        assert result.exit_code == 1
        assert "--agent" in result.stderr

    def test_prompt_is_required(self) -> None:
        result = runner.invoke(app, ["hook", "--agent", "claude"], input="")

        # Missing --prompt must fail open (exit 1), never collide with the
        # exit code (2) reserved exclusively for a verified fail verdict.
        assert result.exit_code == 1
        assert "--prompt" in result.stderr

    def test_unknown_option_exits_one_not_two(self) -> None:
        # An unrecognized option (e.g. a flag from a newer konsistent copied
        # into an older install's hook command) must not trigger Click's
        # UsageError, which exits 2 -- reserved exclusively for a verified
        # fail verdict. The hook command collects unknown options via
        # ignore_unknown_options and fails open with exit 1.
        result = runner.invoke(
            app,
            ["hook", "--agent", "claude", "--prompt", "check it", "--bogus-flag", "x"],
            input="{}",
        )

        assert result.exit_code == 1
        assert "--bogus-flag" in result.stderr

    def test_model_option_is_accepted(self) -> None:
        # --model parses at the CLI layer; with an empty payload the command
        # skips before ever spawning an agent, so exit 0 proves wiring only.
        result = runner.invoke(
            app,
            ["hook", "--agent", "claude", "--prompt", "check it", "--model", "opus"],
            input="",
        )

        assert result.exit_code == 0

    def test_invalid_agent_choice_exits_one_not_two(self) -> None:
        # A stale/typo'd --agent value (e.g. "auto", copied from
        # extract-rules, which is not accepted here) must not be caught by
        # Click's own choice validation -- that would exit 2, indistinguishable
        # from a verified fail verdict to a Claude Code/Codex PostToolUse host.
        result = runner.invoke(
            app, ["hook", "--agent", "auto", "--prompt", "check it"], input="{}"
        )

        assert result.exit_code == 1
        assert "Invalid agent" in result.stderr

    def test_missing_agent_and_missing_prompt_never_exit_two(self) -> None:
        for argv in (
            ["hook", "--agent", "auto", "--prompt", "check it"],
            ["hook", "--prompt", "check it"],
            ["hook", "--agent", "claude"],
        ):
            result = runner.invoke(app, argv, input="{}")
            assert result.exit_code != 2, f"{argv} unexpectedly exited 2: {result.stderr}"

    def test_match_option_repeats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("konsistent.cli.agent_runner.shutil.which", lambda _b: None)
        stdin = payload_json(tool_input={"file_path": "b/x.py"})

        result = runner.invoke(
            app,
            [
                "hook",
                "--agent",
                "claude",
                "--prompt",
                "check it",
                "--match",
                "a/**/*.py",
                "--match",
                "b/**/*.py",
            ],
            input=stdin,
        )

        assert result.exit_code == 1

    def test_match_option_skips_when_none_of_the_repeated_globs_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("konsistent.cli.agent_runner.shutil.which", lambda _b: None)
        stdin = payload_json(tool_input={"file_path": "other/x.py"})

        result = runner.invoke(
            app,
            [
                "hook",
                "--agent",
                "claude",
                "--prompt",
                "check it",
                "--match",
                "a/**/*.py",
                "--match",
                "b/**/*.py",
            ],
            input=stdin,
        )

        assert result.exit_code == 0

    def test_exit_code_propagation_for_skip_via_sentinel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(SENTINEL_ENV, "1")

        result = runner.invoke(
            app,
            ["hook", "--agent", "claude", "--prompt", "check it", "--match", "src/**/*.py"],
            input="",
        )

        assert result.exit_code == 0


class TestRunAgentSubprocessModel:
    def test_model_args_are_injected_before_guard_args_and_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        from konsistent.cli import agent_runner

        captured: dict[str, object] = {}

        def fake_subprocess_run(command, **kwargs):
            captured["command"] = command
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        monkeypatch.setattr(agent_runner.subprocess, "run", fake_subprocess_run)

        invocation = AgentInvocation(agent="claude", executable="claude", prefix_args=("-p",))
        agent_runner.run_agent_subprocess(
            invocation=invocation,
            prompt="verify it",
            extra_args=("--sandbox", "read-only"),
            model="sonnet",
        )

        assert captured["command"] == [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--sandbox",
            "read-only",
            "verify it",
        ]

    def test_no_model_args_when_model_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        from konsistent.cli import agent_runner

        captured: dict[str, object] = {}

        def fake_subprocess_run(command, **kwargs):
            captured["command"] = command
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        monkeypatch.setattr(agent_runner.subprocess, "run", fake_subprocess_run)

        invocation = AgentInvocation(agent="claude", executable="claude", prefix_args=("-p",))
        agent_runner.run_agent_subprocess(invocation=invocation, prompt="verify it")

        assert captured["command"] == ["claude", "-p", "verify it"]


class TestHookFindingLog:
    def test_fail_verdict_appends_one_jsonl_finding(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        log_path = tmp_path / "logs" / "findings.jsonl"
        reason = "method body does not match docstring"
        runner_spy = FakeRunner(verdict_response(verdict="fail", reasons=[reason]))

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            model="opus",
            log_path=str(log_path),
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert reason in captured.err

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["schemaVersion"] == "v1"
        assert record["verdict"] == "fail"
        assert record["filePath"] == "src/x.py"
        assert record["prompt"] == "check it"
        assert record["agent"] == "claude"
        assert record["model"] == "opus"
        assert record["reasons"] == [reason]

    def test_log_append_error_still_exits_two_and_warns_after_reasons(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        reason = "method body does not match docstring"
        runner_spy = FakeRunner(verdict_response(verdict="fail", reasons=[reason]))

        def fake_append_hook_finding(path, finding):
            return Err("boom")

        monkeypatch.setattr(
            "konsistent.cli.hook.append_hook_finding",
            fake_append_hook_finding,
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            log_path="findings.jsonl",
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        captured = capsys.readouterr()
        warning = "konsistent hook: --log warning: boom"
        assert exit_code == 2
        assert reason in captured.err
        assert warning in captured.err
        assert captured.err.index(reason) < captured.err.index(warning)

    def test_pass_verdict_with_log_path_does_not_create_log_file(
        self,
        tmp_path: Path,
    ) -> None:
        log_path = tmp_path / "findings.jsonl"
        runner_spy = FakeRunner(verdict_response(verdict="pass"))

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CLAUDE,
            log_path=str(log_path),
            stdin_text=payload_json(tool_input={"file_path": "src/x.py"}),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 0
        assert not log_path.exists()

    def test_first_fail_among_multiple_matched_paths_logs_only_first_path(
        self,
        tmp_path: Path,
    ) -> None:
        log_path = tmp_path / "findings.jsonl"
        runner_spy = FakeRunner(
            verdict_response(verdict="fail", reasons=["first file is bad"])
        )
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/a.py\n@@\n-old\n+new\n"
            "*** Update File: src/b.py\n@@\n-old\n+new\n"
            "*** End Patch\n"
        )

        exit_code = run_hook_command(
            match=["src/**/*.py"],
            prompt="check it",
            agent=HookAgent.CODEX,
            log_path=str(log_path),
            stdin_text=payload_json(
                tool_name="apply_patch",
                tool_input={"input": patch_text},
            ),
            runner=runner_spy,
            env={},
        )

        assert exit_code == 2
        assert len(runner_spy.calls) == 1
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["filePath"] == "src/a.py"
        assert record["reasons"] == ["first file is bad"]
