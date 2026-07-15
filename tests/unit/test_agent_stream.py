from __future__ import annotations

import io
import json

from konpy.cli._agent_stream import (
    AgentProgressReporter,
    claude_stream_result,
    render_stream_line,
    verbose_extra_args,
)
from konpy.cli.agent_runner import AgentInvocation


def claude_invocation() -> AgentInvocation:
    return AgentInvocation(agent="claude", executable="/fake/bin/claude", prefix_args=("-p",))


def codex_invocation() -> AgentInvocation:
    return AgentInvocation(agent="codex", executable="/fake/bin/codex", prefix_args=("exec",))


def assistant_event(*blocks: dict[str, object]) -> str:
    return json.dumps({"type": "assistant", "message": {"content": list(blocks)}})


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class TestVerboseExtraArgs:
    def test_claude_needs_stream_json_to_emit_anything_before_finishing(self) -> None:
        assert verbose_extra_args("claude") == ("--output-format", "stream-json", "--verbose")

    def test_codex_streams_by_default_and_needs_no_extra_args(self) -> None:
        assert verbose_extra_args("codex") == ()


class TestRenderStreamLine:
    def test_codex_lines_pass_through_from_both_streams(self) -> None:
        assert render_stream_line("codex", "stderr", "workdir: /repo") == "workdir: /repo"
        assert render_stream_line("codex", "stdout", "final message") == "final message"

    def test_blank_lines_are_dropped(self) -> None:
        assert render_stream_line("codex", "stderr", "   ") is None
        assert render_stream_line("claude", "stderr", "") is None

    def test_claude_stderr_passes_through_raw(self) -> None:
        assert render_stream_line("claude", "stderr", "warning: x") == "warning: x"

    def test_claude_init_event_shows_session_and_model(self) -> None:
        line = json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5"})

        assert render_stream_line("claude", "stdout", line) == (
            "session started (model claude-sonnet-5)"
        )

    def test_claude_assistant_text_is_snippeted(self) -> None:
        line = assistant_event({"type": "text", "text": "Analyzing  the\nrules now."})

        assert render_stream_line("claude", "stdout", line) == "Analyzing the rules now."

    def test_claude_long_assistant_text_is_truncated(self) -> None:
        line = assistant_event({"type": "text", "text": "x" * 500})

        rendered = render_stream_line("claude", "stdout", line)
        assert rendered is not None
        assert len(rendered) == 160
        assert rendered.endswith("...")

    def test_claude_tool_use_shows_tool_name(self) -> None:
        line = assistant_event(
            {"type": "tool_use", "name": "Read"},
            {"type": "text", "text": "reading"},
        )

        assert render_stream_line("claude", "stdout", line) == "tool: Read; reading"

    def test_claude_result_event_and_garbage_are_noise(self) -> None:
        result_line = json.dumps({"type": "result", "result": "{}"})

        assert render_stream_line("claude", "stdout", result_line) is None
        assert render_stream_line("claude", "stdout", "not json") is None
        assert render_stream_line("claude", "stdout", "[1, 2]") is None


class TestClaudeStreamResult:
    def test_prefers_terminal_result_event(self) -> None:
        stdout = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "model": "m"}),
                assistant_event({"type": "text", "text": "thinking..."}),
                json.dumps({"type": "result", "subtype": "success", "result": '{"pack": 1}'}),
            ]
        )

        assert claude_stream_result(stdout) == '{"pack": 1}'

    def test_falls_back_to_assistant_text_blocks(self) -> None:
        stdout = "\n".join(
            [
                assistant_event({"type": "text", "text": "part one"}),
                assistant_event({"type": "text", "text": "part two"}),
            ]
        )

        assert claude_stream_result(stdout) == "part one\npart two"

    def test_falls_back_to_raw_stdout_when_no_events_parse(self) -> None:
        assert claude_stream_result("plain response") == "plain response"


class TestAgentProgressReporter:
    def make_reporter(
        self, *, verbose: bool = False, agent: str = "claude"
    ) -> tuple[AgentProgressReporter, io.StringIO, FakeClock]:
        stream = io.StringIO()
        clock = FakeClock()
        invocation = claude_invocation() if agent == "claude" else codex_invocation()
        reporter = AgentProgressReporter(
            command="extract-rules",
            invocation=invocation,
            model="sonnet",
            verbose=verbose,
            stream=stream,
            clock=clock,
        )
        return reporter, stream, clock

    def test_announce_names_agent_model_and_detail(self) -> None:
        reporter, stream, _clock = self.make_reporter()

        reporter.announce("extracting from rules.md (prompt 42 chars)")

        assert stream.getvalue() == (
            "konpy extract-rules: extracting from rules.md (prompt 42 chars) "
            'via "claude" --model sonnet (typically takes a few minutes)...\n'
        )

    def test_heartbeat_reports_elapsed_seconds(self) -> None:
        reporter, stream, _clock = self.make_reporter()

        reporter.on_progress(30.2)

        assert stream.getvalue() == (
            'konpy extract-rules: still waiting for "claude" (30s elapsed)...\n'
        )

    def test_finish_reports_total_elapsed_from_clock(self) -> None:
        reporter, stream, clock = self.make_reporter()
        clock.now += 92.0

        reporter.finish()

        assert stream.getvalue() == (
            'konpy extract-rules: agent "claude" finished in 92s.\n'
        )

    def test_output_line_callback_is_none_when_not_verbose(self) -> None:
        reporter, _stream, _clock = self.make_reporter(verbose=False)

        assert reporter.output_line_callback is None
        assert reporter.extra_args == ()

    def test_verbose_renders_agent_output_with_agent_prefix(self) -> None:
        reporter, stream, _clock = self.make_reporter(verbose=True, agent="codex")

        assert reporter.output_line_callback is not None
        reporter.on_output_line("stderr", "session id: 123")

        assert stream.getvalue() == "codex> session id: 123\n"

    def test_verbose_claude_gets_stream_json_extra_args(self) -> None:
        reporter, _stream, _clock = self.make_reporter(verbose=True)

        assert reporter.extra_args == ("--output-format", "stream-json", "--verbose")

    def test_recent_verbose_output_suppresses_heartbeat(self) -> None:
        reporter, stream, clock = self.make_reporter(verbose=True, agent="codex")
        reporter.on_output_line("stderr", "busy line")
        clock.now += 2.0

        reporter.on_progress(12.0)

        assert "still waiting" not in stream.getvalue()

    def test_stale_verbose_output_lets_heartbeat_through(self) -> None:
        reporter, stream, clock = self.make_reporter(verbose=True, agent="codex")
        reporter.on_output_line("stderr", "busy line")
        clock.now += 30.0

        reporter.on_progress(31.0)

        assert 'still waiting for "codex" (31s elapsed)' in stream.getvalue()

    def test_finalize_stdout_unwraps_claude_stream_json_only_when_verbose(self) -> None:
        verbose_reporter, _stream, _clock = self.make_reporter(verbose=True)
        quiet_reporter, _stream2, _clock2 = self.make_reporter(verbose=False)
        stream_json = json.dumps({"type": "result", "result": "the response"})

        assert verbose_reporter.finalize_stdout(stream_json) == "the response"
        assert quiet_reporter.finalize_stdout(stream_json) == stream_json

    def test_finalize_stdout_is_identity_for_codex(self) -> None:
        reporter, _stream, _clock = self.make_reporter(verbose=True, agent="codex")

        assert reporter.finalize_stdout("raw output") == "raw output"
