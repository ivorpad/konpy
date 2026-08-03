from __future__ import annotations

import os
from pathlib import Path

import pytest


def write_claude_diff_stub(path: Path, diff_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        f"print({diff_text!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


_STUB_DIFF = (
    "--- a/src/a.py\n"
    "+++ b/src/a.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def calculate_a(value):\n"
    "-    total = value + 1\n"
    "+    return _shared(value)\n"
    "\n"
    "Rationale: extracted the shared body into one helper function."
)


def test_improve_emits_the_stub_agents_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
    run_cli,
) -> None:
    fixture_dir = fixtures_dir / "improve-duplicate-functions"

    stub_bin = tmp_path / "bin"
    write_claude_diff_stub(stub_bin / "claude", _STUB_DIFF)
    monkeypatch.setenv(
        "PATH",
        f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )

    exit_code, stdout, stderr = run_cli(fixture_dir, "improve", "--agent", "auto")

    assert exit_code == 0
    assert stdout.strip() == _STUB_DIFF
    assert 'konpy improve: proposing a fix for "calculate_a"' in stderr
    assert 'via "claude" --model sonnet' in stderr
    assert "finished in" in stderr

    # konpy improve never touches any file in the fixture tree.
    assert (fixture_dir / "src" / "a.py").read_text(encoding="utf-8").startswith(
        "def calculate_a(value):"
    )


def test_improve_no_agent_on_path_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
    run_cli,
) -> None:
    fixture_dir = fixtures_dir / "improve-duplicate-functions"
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    exit_code, _stdout, stderr = run_cli(fixture_dir, "improve", "--agent", "auto")

    assert exit_code == 1
    assert "No supported agent CLI found on PATH" in stderr
