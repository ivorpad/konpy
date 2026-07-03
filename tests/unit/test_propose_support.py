from __future__ import annotations

from konpy.cli._hook_findings import HookFinding
from konpy.cli._propose_support import aggregate_findings


def _finding(
    *,
    prompt: str,
    file_path: str,
    reasons: list[str],
    agent: str = "claude",
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        agent=agent,
        model="sonnet",
        reasons=reasons,
    )


def test_aggregate_findings_groups_by_exact_prompt_and_sorts_by_count_then_prompt() -> None:
    findings = [
        _finding(
            prompt="Prompt A",
            file_path="src/a1.py",
            reasons=["a-reason-1"],
            agent="claude",
        ),
        _finding(
            prompt="Prompt B",
            file_path="src/b1.py",
            reasons=["b-reason-1", "b-reason-2"],
            agent="codex",
        ),
        _finding(
            prompt="Prompt C",
            file_path="src/c1.py",
            reasons=["c-reason-1"],
            agent="claude",
        ),
        _finding(
            prompt="Prompt B",
            file_path="src/b1.py",
            reasons=["b-reason-2", "b-reason-3"],
            agent="claude",
        ),
        _finding(
            prompt="Prompt A",
            file_path="src/a2.py",
            reasons=["a-reason-2"],
            agent="codex",
        ),
        _finding(
            prompt="Prompt B",
            file_path="src/b2.py",
            reasons=["b-reason-3", "b-reason-4"],
            agent="codex",
        ),
        _finding(
            prompt="Prompt B",
            file_path="src/b3.py",
            reasons=["b-reason-5"],
            agent="codex",
        ),
        _finding(
            prompt="Prompt C",
            file_path="src/c2.py",
            reasons=["c-reason-2"],
            agent="codex",
        ),
    ]

    aggregated = aggregate_findings(findings, max_files=2, max_reasons=2)

    assert [item.prompt for item in aggregated] == ["Prompt B", "Prompt A", "Prompt C"]

    prompt_b = aggregated[0]
    assert prompt_b.occurrences == 4
    assert prompt_b.agent == "codex"
    assert prompt_b.file_paths == ("src/b1.py", "src/b2.py")
    assert prompt_b.reasons == ("b-reason-1", "b-reason-2")

    prompt_a = aggregated[1]
    assert prompt_a.occurrences == 2
    assert prompt_a.agent == "claude"
    assert prompt_a.file_paths == ("src/a1.py", "src/a2.py")
    assert prompt_a.reasons == ("a-reason-1", "a-reason-2")

    prompt_c = aggregated[2]
    assert prompt_c.occurrences == 2
    assert prompt_c.agent == "claude"
    assert prompt_c.file_paths == ("src/c1.py", "src/c2.py")
    assert prompt_c.reasons == ("c-reason-1", "c-reason-2")


def test_aggregate_findings_empty_input_returns_empty_list() -> None:
    assert aggregate_findings([]) == []
