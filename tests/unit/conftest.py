from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_github_actions_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests hermetic against the reporter's CI auto-detection.

    ``resolve_format`` promotes the ``default`` format to ``github`` annotation
    output when ``GITHUB_ACTIONS == "true"``. In-process CLI tests assert on the
    human-readable default output, so they must not observe the runner's own
    ``GITHUB_ACTIONS`` variable. Tests that exercise the auto-detection pass an
    explicit ``env=`` mapping and are unaffected by this.
    """
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
