from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify"

# scripts/verify full runs `pytest -q`, which would re-collect and re-run this
# very module — an infinite recursion. KONPY_VERIFY_ACTIVE is set on every
# child process scripts/verify spawns, so tests here skip whenever they are
# themselves running underneath a scripts/verify invocation.
pytestmark = pytest.mark.skipif(
    os.environ.get("KONPY_VERIFY_ACTIVE") is not None,
    reason="scripts/verify full runs pytest, which would re-run this module recursively",
)


def _hook_pre_payload(*, file_path: str, content: str) -> str:
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
            "cwd": str(REPO_ROOT),
        }
    )


class TestVerifyFastSmoke:
    def test_fast_profile_exits_zero_on_the_current_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "fast"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr


class TestVerifyHookPre:
    def test_violating_write_exits_two(self) -> None:
        # hook-pre gates on konpy.strict.json, which rejects this proposed
        # write (an undocumented public function in src/konpy). The exact
        # rule that fires is policy detail owned by the config, so assert
        # the stable contract instead: a deterministic block with the
        # gate's JSON diagnostics on stderr.
        payload = _hook_pre_payload(
            file_path="src/konpy/core/_verify_probe.py",
            content="from konpy.cli import app\n\n\ndef use() -> object:\n    return app\n",
        )

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "hook-pre"],
            cwd=REPO_ROOT,
            input=payload,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 2
        assert result.stdout == ""
        assert '"diagnostics"' in result.stderr

    def test_benign_write_outside_any_convention_exits_zero(self) -> None:
        payload = _hook_pre_payload(
            file_path="docs/_verify_probe_benign.md",
            content="# probe\n",
        )

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "hook-pre"],
            cwd=REPO_ROOT,
            input=payload,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""
