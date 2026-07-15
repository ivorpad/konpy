from __future__ import annotations

from konpy.cli._hook_findings import HookFinding
from konpy.cli._propose_support import aggregate_findings


def finding(
    *,
    prompt: str,
    file_path: str,
    reasons: list[str],
    agent: str = "claude",
    rule: str | None = None,
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        rule=rule,
        agent=agent,
        model="sonnet",
        reasons=reasons,
    )


def test_aggregation_groups_by_exact_prompt_not_rule_metadata() -> None:
    findings = [
        finding(
            prompt="Prompt A",
            rule="rule-a",
            file_path="src/a1.py",
            reasons=["a-reason-1"],
        ),
        finding(
            prompt="Prompt B",
            rule="rule-b",
            file_path="src/b1.py",
            reasons=["b-reason-1", "b-reason-2"],
            agent="codex",
        ),
        finding(
            prompt="Prompt B",
            rule="renamed-rule-b",
            file_path="src/b1.py",
            reasons=["b-reason-2", "b-reason-3"],
        ),
        finding(
            prompt="Prompt A",
            rule=None,
            file_path="src/a2.py",
            reasons=["a-reason-2"],
            agent="codex",
        ),
        finding(
            prompt="Prompt B",
            rule="rule-b",
            file_path="src/b2.py",
            reasons=["b-reason-4"],
            agent="codex",
        ),
    ]

    aggregated = aggregate_findings(
        findings,
        max_files=2,
        max_reasons=3,
    )

    assert [item.prompt for item in aggregated] == ["Prompt B", "Prompt A"]

    prompt_b = aggregated[0]
    assert prompt_b.occurrences == 3
    assert prompt_b.agent == "codex"
    assert prompt_b.file_paths == ("src/b1.py", "src/b2.py")
    assert prompt_b.reasons == (
        "b-reason-1",
        "b-reason-2",
        "b-reason-3",
    )

    prompt_a = aggregated[1]
    assert prompt_a.occurrences == 2
    assert prompt_a.agent == "claude"
    assert prompt_a.file_paths == ("src/a1.py", "src/a2.py")
    assert prompt_a.reasons == ("a-reason-1", "a-reason-2")


def test_different_rule_prompts_promote_independently() -> None:
    aggregated = aggregate_findings(
        [
            finding(
                prompt="Verify contextual errors.",
                rule="contextual-errors",
                file_path="src/a.py",
                reasons=["missing context"],
            ),
            finding(
                prompt="Verify honest docstrings.",
                rule="honest-docstrings",
                file_path="src/a.py",
                reasons=["docstring overclaims"],
            ),
        ]
    )

    assert [item.prompt for item in aggregated] == [
        "Verify contextual errors.",
        "Verify honest docstrings.",
    ]
    assert [item.occurrences for item in aggregated] == [1, 1]


def test_limits_preserve_first_seen_unique_values() -> None:
    aggregated = aggregate_findings(
        [
            finding(
                prompt="Prompt",
                file_path="src/a.py",
                reasons=["one", "two"],
            ),
            finding(
                prompt="Prompt",
                file_path="src/a.py",
                reasons=["two", "three"],
            ),
            finding(
                prompt="Prompt",
                file_path="src/b.py",
                reasons=["four"],
            ),
        ],
        max_files=1,
        max_reasons=2,
    )

    assert aggregated[0].file_paths == ("src/a.py",)
    assert aggregated[0].reasons == ("one", "two")


def test_empty_input_returns_empty_list() -> None:
    assert aggregate_findings([]) == []
