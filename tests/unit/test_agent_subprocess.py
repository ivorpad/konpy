from __future__ import annotations

import sys

from konpy.cli.agent_runner import AgentInvocation, run_agent_subprocess


def python_invocation(agent: str = "claude") -> AgentInvocation:
    """A real-subprocess invocation that executes the prompt as Python code."""
    return AgentInvocation(agent=agent, executable=sys.executable, prefix_args=("-c",))


class TestStreamingSubprocess:
    def test_captures_output_and_relays_lines_to_callback(self) -> None:
        lines: list[tuple[str, str]] = []

        result = run_agent_subprocess(
            invocation=python_invocation(),
            prompt=(
                "import sys\n"
                "print('out one')\n"
                "print('out two')\n"
                "print('err one', file=sys.stderr)\n"
            ),
            on_output_line=lambda stream, line: lines.append((stream, line)),
        )

        assert result.returncode == 0
        assert result.stdout == "out one\nout two\n"
        assert result.stderr == "err one\n"
        assert ("stdout", "out one") in lines
        assert ("stdout", "out two") in lines
        assert ("stderr", "err one") in lines

    def test_on_progress_fires_with_increasing_elapsed(self) -> None:
        ticks: list[float] = []

        result = run_agent_subprocess(
            invocation=python_invocation(),
            prompt="import time; time.sleep(0.5)",
            on_progress=ticks.append,
            progress_interval=0.05,
        )

        assert result.returncode == 0
        assert len(ticks) >= 2
        assert ticks == sorted(ticks)
        assert all(tick > 0 for tick in ticks)

    def test_timeout_kills_process_and_matches_blocking_contract(self) -> None:
        result = run_agent_subprocess(
            invocation=python_invocation(),
            prompt="import time; time.sleep(30)",
            timeout=0.3,
            on_progress=lambda _elapsed: None,
            progress_interval=0.05,
        )

        assert result.returncode == 124
        assert result.timed_out is True
        assert result.stdout == ""
        assert result.stderr == 'Agent CLI "claude" timed out after 0.3s.'

    def test_missing_executable_returns_127_like_blocking_path(self) -> None:
        invocation = AgentInvocation(
            agent="claude",
            executable="/nonexistent/definitely-not-a-binary",
            prefix_args=("-p",),
        )

        result = run_agent_subprocess(
            invocation=invocation,
            prompt="hi",
            on_progress=lambda _elapsed: None,
        )

        assert result.returncode == 127
        assert result.timed_out is False
        assert 'Could not start agent CLI "claude":' in result.stderr

    def test_output_callback_errors_do_not_break_capture(self) -> None:
        def broken_callback(_stream: str, _line: str) -> None:
            raise RuntimeError("progress rendering bug")

        result = run_agent_subprocess(
            invocation=python_invocation(),
            prompt="print('still captured')",
            on_output_line=broken_callback,
        )

        assert result.returncode == 0
        assert result.stdout == "still captured\n"

    def test_extra_args_precede_prompt_in_streaming_path(self) -> None:
        # With ("-c",) prefix args, the first extra arg is executed as code
        # and the prompt lands in sys.argv[1:] -- proving arg order matches
        # the blocking path: extra_args before prompt.
        result = run_agent_subprocess(
            invocation=python_invocation(),
            prompt="THE_PROMPT",
            extra_args=("import sys; print(sys.argv[1:])",),
            on_output_line=lambda _stream, _line: None,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "['THE_PROMPT']"
