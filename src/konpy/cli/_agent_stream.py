"""Progress reporting and verbose output rendering for interactive agent runs.

`extract-rules` and `hook-propose` wrap their agent subprocess in an
`AgentProgressReporter`: an announce line before the run, a heartbeat while
waiting, the agent's own streamed output under `--verbose`, and a finish line.
Everything goes to stderr so stdout keeps carrying only the result lines.
`konpy hook` deliberately does not use any of this.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from typing import TextIO

from konpy.cli.agent_runner import AgentInvocation

PROGRESS_INTERVAL = 10.0

_SNIPPET_LENGTH = 160

_CLAUDE_VERBOSE_ARGS = ("--output-format", "stream-json", "--verbose")


class AgentProgressReporter:
    """Writes announce/heartbeat/finish lines for one agent subprocess run.

    Only constructed on the real-subprocess path; injectable-runner test runs
    stay silent. With `verbose`, also renders the agent CLI's own output live
    and knows how to recover the final response text from claude's stream-json
    output.
    """

    def __init__(
        self,
        *,
        command: str,
        invocation: AgentInvocation,
        model: str,
        verbose: bool,
        stream: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._command = command
        self._invocation = invocation
        self._model = model
        self._verbose = verbose
        self._stream = stream
        self._clock = clock
        self._started_at = clock()
        self._last_output_at: float | None = None

    @property
    def extra_args(self) -> tuple[str, ...]:
        """Extra agent CLI args needed for verbose streaming, if any."""
        if self._verbose:
            return verbose_extra_args(self._invocation.agent)
        return ()

    @property
    def output_line_callback(self) -> Callable[[str, str], None] | None:
        """The per-line callback for `run_agent_subprocess`, or None when quiet."""
        if self._verbose:
            return self.on_output_line
        return None

    def announce(self, detail: str) -> None:
        """Write the pre-run line, e.g. what is being extracted and via what."""
        self._write(
            f'{detail} via "{self._invocation.agent}" --model {self._model}'
            " (typically takes a few minutes)..."
        )

    def on_progress(self, elapsed: float) -> None:
        """Write a heartbeat unless verbose output just showed activity."""
        if (
            self._last_output_at is not None
            and self._clock() - self._last_output_at < PROGRESS_INTERVAL
        ):
            return
        self._write(
            f'still waiting for "{self._invocation.agent}" ({elapsed:.0f}s elapsed)...'
        )

    def on_output_line(self, stream_name: str, line: str) -> None:
        """Render one line of the agent's own output (verbose mode only)."""
        rendered = render_stream_line(self._invocation.agent, stream_name, line)
        if rendered is None:
            return
        self._last_output_at = self._clock()
        target = self._stream if self._stream is not None else sys.stderr
        target.write(f"{self._invocation.agent}> {rendered}\n")
        target.flush()

    def finish(self) -> None:
        """Write the post-run line with the total elapsed time."""
        elapsed = self._clock() - self._started_at
        self._write(f'agent "{self._invocation.agent}" finished in {elapsed:.0f}s.')

    def finalize_stdout(self, stdout: str) -> str:
        """Recover the agent's response text from captured stdout.

        Claude's stream-json mode wraps the response in JSONL events; without
        verbose (or for codex) stdout is already the response.
        """
        if self._verbose and self._invocation.agent == "claude":
            return claude_stream_result(stdout)
        return stdout

    def _write(self, message: str) -> None:
        target = self._stream if self._stream is not None else sys.stderr
        target.write(f"konpy {self._command}: {message}\n")
        target.flush()


def verbose_extra_args(agent: str) -> tuple[str, ...]:
    """Agent CLI args that turn on live output for `agent`.

    `claude -p` prints nothing until it finishes unless asked for stream-json;
    `codex exec` already streams human-readable progress to stderr.
    """
    if agent == "claude":
        return _CLAUDE_VERBOSE_ARGS
    return ()


def render_stream_line(agent: str, stream_name: str, line: str) -> str | None:
    """Turn one raw output line into a short human-readable progress line.

    Returns None for noise (blank lines, unparseable or uninteresting claude
    events). Codex output and any agent's stderr pass through as-is.
    """
    if agent != "claude" or stream_name == "stderr":
        return line if line.strip() else None
    return _render_claude_event(line)


def claude_stream_result(stdout: str) -> str:
    """Extract the final response text from claude stream-json output.

    Prefers the `result` field of the terminal result event, falls back to
    concatenated assistant text blocks, then to the raw stdout.
    """
    result_text: str | None = None
    assistant_texts: list[str] = []

    for line in stdout.splitlines():
        event = _decode_event(line)
        if event is None:
            continue
        result_value = event.get("result")
        if event.get("type") == "result" and isinstance(result_value, str):
            result_text = result_value
        elif event.get("type") == "assistant":
            assistant_texts.extend(
                text for text, _is_tool in _claude_message_parts(event)
            )

    if result_text is not None:
        return result_text
    if assistant_texts:
        return "\n".join(assistant_texts)
    return stdout


def _render_claude_event(line: str) -> str | None:
    event = _decode_event(line)
    if event is None:
        return None

    if event.get("type") == "system" and event.get("subtype") == "init":
        model = event.get("model")
        return f"session started (model {model})" if isinstance(model, str) else None

    if event.get("type") == "assistant":
        parts = [
            f"tool: {text}" if is_tool else _snippet(text)
            for text, is_tool in _claude_message_parts(event)
        ]
        rendered = "; ".join(part for part in parts if part)
        return rendered or None

    return None


def _claude_message_parts(event: dict[str, object]) -> list[tuple[str, bool]]:
    """Yield `(text, is_tool_use)` for each content block of an assistant event."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []

    parts: list[tuple[str, bool]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append((block["text"], False))
        elif block.get("type") == "tool_use":
            name = block.get("name")
            parts.append((name if isinstance(name, str) else "?", True))
    return parts


def _decode_event(line: str) -> dict[str, object] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _SNIPPET_LENGTH:
        return collapsed
    return collapsed[: _SNIPPET_LENGTH - 3] + "..."


__all__ = [
    "PROGRESS_INTERVAL",
    "AgentProgressReporter",
    "claude_stream_result",
    "render_stream_line",
    "verbose_extra_args",
]
