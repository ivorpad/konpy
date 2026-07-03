from __future__ import annotations

from konpy.cli._propose_prompt import build_propose_prompt
from konpy.cli._propose_support import AggregatedFinding


def test_build_propose_prompt_embeds_contract_rubrics_evidence_and_predicates() -> None:
    first_prompt = "Verify docstrings are not aspirational.\nInspect the implementation."
    second_prompt = "Verify service names match exported classes."
    prompt = build_propose_prompt(
        aggregated=[
            AggregatedFinding(
                prompt=first_prompt,
                agent="claude",
                occurrences=2,
                file_paths=("src/service.py", "src/other_service.py"),
                reasons=("docstring overclaims behavior", "method body disagrees"),
            ),
            AggregatedFinding(
                prompt=second_prompt,
                agent="codex",
                occurrences=1,
                file_paths=("src/user_service.py",),
                reasons=("missing matching exported class",),
            ),
        ],
        predicates_reference="# Predicates\n\n## haveType\n",
    )

    assert "You convert recurring konpy hook agentic verification failures" in prompt
    assert "reviewable reusable convention pack" in prompt
    assert "Mappability rubric:" in prompt
    assert "insufficient evidence" in prompt
    assert "Never propose or reference a konpy ignore suppression comment" in prompt
    assert "require explicit human approval and are out of scope" in prompt

    first_header = "## Finding group 1 (occurrences: 2, agent: claude)"
    second_header = "## Finding group 2 (occurrences: 1, agent: codex)"
    assert first_header in prompt
    assert second_header in prompt
    assert prompt.index(first_header) < prompt.index(second_header)

    assert f"--- PROMPT START ---\n{first_prompt}\n--- PROMPT END ---" in prompt
    assert f"--- PROMPT START ---\n{second_prompt}\n--- PROMPT END ---" in prompt
    assert "- src/service.py" in prompt
    assert "- src/other_service.py" in prompt
    assert "- src/user_service.py" in prompt
    assert "- docstring overclaims behavior" in prompt
    assert "- method body disagrees" in prompt
    assert "- missing matching exported class" in prompt

    assert (
        "--- FULL docs/reference/predicates.md START ---\n"
        "# Predicates\n\n"
        "## haveType\n"
        "\n--- FULL docs/reference/predicates.md END ---"
    ) in prompt
