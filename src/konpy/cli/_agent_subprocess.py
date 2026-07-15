"""Popen-based agent subprocess execution with progress and output-line callbacks.

Used by `run_agent_subprocess` when a caller asks for progress feedback; the
plain `subprocess.run` path stays in `agent_runner.py` for callback-free runs.
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time
from collections.abc import Callable
from typing import IO


def run_streaming_subprocess(
    *,
    command: list[str],
    agent_label: str,
    timeout: float | None,
    env: dict[str, str] | None,
    on_progress: Callable[[float], None] | None,
    progress_interval: float,
    on_output_line: Callable[[str, str], None] | None,
) -> tuple[int, str, str, bool]:
    """Run `command`, relaying progress ticks and output lines while it runs.

    Returns `(returncode, stdout, stderr, timed_out)` with the same error
    conventions as the blocking path: 127 when the executable cannot start,
    124 with `timed_out=True` when `timeout` elapses. `on_progress` receives
    the elapsed seconds roughly every `progress_interval`; `on_output_line`
    receives `("stdout" | "stderr", line)` as the child produces output.
    stdin is closed (`/dev/null`) so a child that polls it cannot stall an
    interactive run.
    """
    try:
        process = subprocess.Popen(
            command,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as error:
        return 127, "", f'Could not start agent CLI "{agent_label}": {error}', False

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    readers = [
        threading.Thread(
            target=_drain,
            args=(process.stdout, "stdout", stdout_lines, on_output_line),
            daemon=True,
        ),
        threading.Thread(
            target=_drain,
            args=(process.stderr, "stderr", stderr_lines, on_output_line),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        if timeout is not None and elapsed >= timeout:
            process.kill()
            process.wait()
            for reader in readers:
                reader.join()
            return (
                124,
                "",
                f'Agent CLI "{agent_label}" timed out after {timeout}s.',
                True,
            )

        wait_for = progress_interval
        if timeout is not None:
            wait_for = min(wait_for, timeout - elapsed)
        try:
            process.wait(timeout=max(wait_for, 0.01))
            break
        except subprocess.TimeoutExpired:
            if on_progress is not None:
                on_progress(time.monotonic() - started)

    for reader in readers:
        reader.join()
    return process.returncode, "".join(stdout_lines), "".join(stderr_lines), False


def _drain(
    pipe: IO[str] | None,
    stream_name: str,
    sink: list[str],
    on_output_line: Callable[[str, str], None] | None,
) -> None:
    """Read `pipe` to EOF, buffering every line and relaying it to the callback.

    Callback errors are suppressed: a progress-rendering bug must not stop
    draining, or the child would block on a full pipe and never exit.
    """
    if pipe is None:
        return
    with pipe:
        for line in pipe:
            sink.append(line)
            if on_output_line is not None:
                with contextlib.suppress(Exception):
                    on_output_line(stream_name, line.rstrip("\r\n"))


__all__ = ["run_streaming_subprocess"]
