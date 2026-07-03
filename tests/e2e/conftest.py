from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import _preprocess_argv, app


def _make_runner() -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


_RUNNER = _make_runner()


@contextmanager
def _chdir(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _invoke(
    fixture_dir: str | Path, args: tuple[str, ...], *, stdin: str | None = None
) -> tuple[int, str, str]:
    path = Path(fixture_dir)
    argv = _preprocess_argv([str(arg) for arg in args])

    with _chdir(path):
        result = _RUNNER.invoke(
            app,
            argv,
            input=stdin,
            color=False,
            env={**os.environ, "GITHUB_ACTIONS": ""},
        )

    stdout = getattr(result, "stdout", None)
    if stdout is None:
        stdout = result.output

    try:
        stderr = result.stderr
    except ValueError:
        stderr = ""

    return result.exit_code, stdout, stderr


def run_cli(fixture_dir: str | Path, *args: str) -> tuple[int, str, str]:
    return _invoke(fixture_dir, args)


def run_cli_stdin(fixture_dir: str | Path, stdin: str, *args: str) -> tuple[int, str, str]:
    """Thin additive variant of run_cli that forwards `stdin` to the CLI process."""
    return _invoke(fixture_dir, args, stdin=stdin)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(name="run_cli")
def run_cli_fixture() -> Callable[..., tuple[int, str, str]]:
    return run_cli


@pytest.fixture(name="run_cli_stdin")
def run_cli_stdin_fixture() -> Callable[..., tuple[int, str, str]]:
    return run_cli_stdin
