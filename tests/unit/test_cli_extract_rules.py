from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from konpy.cli.extract_rules import (
    AgentInvocation,
    AgentRunResult,
    ExtractAgent,
    build_prompt,
    extract_agent_json_object,
    run_extract_rules_command,
    select_agent_invocation,
    validate_agent_response_contract,
)
from konpy.config.errors import Err, Ok

_MISSING = object()


def reusable_pack() -> dict[str, Any]:
    return {
        "conventionSpecVersion": "v1",
        "conventions": [
            {
                "name": "source-files-are-files",
                "description": "Source files should be regular files.",
                "paths": "src/*.py",
                "must": {"haveType": "file"},
            }
        ],
    }


def semantic_rules() -> list[dict[str, object]]:
    return [
        {
            "name": "use-contextual-errors",
            "prompt": "Verify that raised errors explain the failed operation.",
            "match": ["src/**/*.py"],
            "source": "Errors must explain the failed operation.",
        }
    ]


def covered_rules() -> list[dict[str, str]]:
    return [
        {
            "rule": "Mutable class defaults must be annotated.",
            "tool": "ruff RUF012",
            "note": "Ruff already detects mutable class defaults.",
        }
    ]


def agent_response(
    *,
    pack: dict[str, Any] | None = None,
    semantic: object = _MISSING,
    covered_elsewhere: object = _MISSING,
    unmapped: object | None = None,
) -> str:
    payload: dict[str, object] = {
        "pack": reusable_pack() if pack is None else pack,
        "unmapped": [] if unmapped is None else unmapped,
    }
    if semantic is not _MISSING:
        payload["semantic"] = semantic
    if covered_elsewhere is not _MISSING:
        payload["coveredElsewhere"] = covered_elsewhere
    return json.dumps(payload)


def write_source(path: Path) -> None:
    path.write_text(
        "# Team rules\n\n"
        "Every source file must be a file.\n"
        "Errors must explain the failed operation.\n",
        encoding="utf-8",
    )


class FakeRunner:
    def __init__(self, response: AgentRunResult | str) -> None:
        self.response = response
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(
        self,
        invocation: AgentInvocation,
        prompt: str,
    ) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        return self.response


class TestPromptAssembly:
    def test_prompt_contains_four_lane_contract_and_routing_order(self) -> None:
        prompt = build_prompt(
            source_text="Use contextual errors.",
            source_label="rules.md",
            predicates_reference="# Predicates\n\n## matchContent\n",
        )

        assert '"pack"' in prompt
        assert '"semantic"' in prompt
        assert '"coveredElsewhere"' in prompt
        assert '"unmapped"' in prompt
        assert "Routing order:" in prompt
        assert "Ruff or mypy" in prompt
        assert "single\n   changed file" in prompt
        assert "repository-wide, runtime, operational, or process" in prompt
        assert "Every source rule must land in exactly" in prompt
        assert "self-contained verification instruction" in prompt
        assert "weak matchContent approximation" in prompt
        assert "Do not invent predicate keys" in prompt
        assert "konpy.json" in prompt


class TestJsonExtraction:
    def test_accepts_raw_fenced_and_prose_wrapped_json(self) -> None:
        raw = agent_response()
        for response in (
            raw,
            f"```json\n{raw}\n```",
            f"Here is the proposal:\n{raw}\nDone.",
        ):
            result = extract_agent_json_object(response)
            assert isinstance(result, Ok)
            assert result.value["pack"] == reusable_pack()

    def test_prefers_object_with_required_contract_keys(self) -> None:
        response = '{"incidental": true}\n' + agent_response()

        result = extract_agent_json_object(response)

        assert isinstance(result, Ok)
        assert "pack" in result.value
        assert "unmapped" in result.value

    def test_returns_error_when_no_json_object_exists(self) -> None:
        result = extract_agent_json_object("No JSON here.")

        assert isinstance(result, Err)
        assert result.error == "Agent response did not contain a valid JSON object."


class TestContractValidation:
    def test_optional_lanes_default_to_empty_lists(self) -> None:
        result = validate_agent_response_contract(
            {
                "pack": reusable_pack(),
                "unmapped": [],
            }
        )

        assert isinstance(result, Ok)
        pack, semantic, covered, unmapped = result.value
        assert pack == reusable_pack()
        assert semantic == []
        assert covered == []
        assert unmapped == []

    def test_all_lanes_are_normalized(self) -> None:
        result = validate_agent_response_contract(
            {
                "pack": reusable_pack(),
                "semantic": semantic_rules(),
                "coveredElsewhere": [
                    {
                        **covered_rules()[0],
                        "ignored": "discarded",
                    }
                ],
                "unmapped": [
                    {
                        "rule": "Adopt a review rotation.",
                        "reason": "This is process guidance.",
                        "ignored": "discarded",
                    }
                ],
            }
        )

        assert isinstance(result, Ok)
        _pack, semantic, covered, unmapped = result.value
        assert semantic[0].name == "use-contextual-errors"
        assert covered == covered_rules()
        assert unmapped == [
            {
                "rule": "Adopt a review rotation.",
                "reason": "This is process guidance.",
            }
        ]

    @pytest.mark.parametrize("missing_key", ["pack", "unmapped"])
    def test_required_lanes_must_be_present(self, missing_key: str) -> None:
        payload: dict[str, object] = {
            "pack": reusable_pack(),
            "unmapped": [],
        }
        del payload[missing_key]

        result = validate_agent_response_contract(payload)

        assert isinstance(result, Err)
        assert 'expected keys "pack" and "unmapped"' in result.error

    @pytest.mark.parametrize("value", [{}, "semantic", None])
    def test_semantic_must_be_a_list(self, value: object) -> None:
        result = validate_agent_response_contract(
            {
                "pack": reusable_pack(),
                "semantic": value,
                "unmapped": [],
            }
        )

        assert isinstance(result, Err)
        assert '"semantic" must be a list' in result.error

    @pytest.mark.parametrize(
        "value",
        [
            {},
            [{"rule": "Use Ruff."}],
            [{"rule": "Use Ruff.", "tool": 12}],
            [{"rule": "Use Ruff.", "tool": "ruff", "note": 12}],
        ],
    )
    def test_covered_elsewhere_shape_is_validated(self, value: object) -> None:
        result = validate_agent_response_contract(
            {
                "pack": reusable_pack(),
                "coveredElsewhere": value,
                "unmapped": [],
            }
        )

        assert isinstance(result, Err)
        assert '"coveredElsewhere" must be a list' in result.error


class TestRunExtractRulesCommand:
    def test_four_lane_response_writes_both_artifacts_and_inline_report(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(
                agent_response(
                    semantic=semantic_rules(),
                    covered_elsewhere=covered_rules(),
                    unmapped=[
                        {
                            "rule": "Rotate reviewers weekly.",
                            "reason": "This is process guidance.",
                        }
                    ],
                )
            ),
        )

        captured = capsys.readouterr()
        rules_path = tmp_path / "packs" / "team.rules.json"
        assert exit_code == 0
        assert captured.err == ""
        assert json.loads(output.read_text(encoding="utf-8")) == reusable_pack()
        written_rules = json.loads(rules_path.read_text(encoding="utf-8"))
        assert written_rules == {
            "semanticRulesSpecVersion": "v1",
            "rules": semantic_rules(),
        }
        assert f"Wrote semantic rules to {rules_path}" in captured.out
        assert "Covered by existing linters:" in captured.out
        assert (
            "- Mutable class defaults must be annotated.: ruff RUF012 "
            "— Ruff already detects mutable class defaults."
        ) in captured.out
        assert "Unmapped rules:" in captured.out
        assert "Rotate reviewers weekly.: This is process guidance." in captured.out
        assert (
            "Add a PostToolUse hook: konpy hook --match '**/*.py' "
            f"--rules {rules_path} --agent claude"
        ) in captured.out

    def test_default_paths_use_source_stem_under_packs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "team-rules.md"
        write_source(source)
        monkeypatch.chdir(tmp_path)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=None,
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        assert exit_code == 0
        assert (tmp_path / "packs" / "team-rules.json").exists()
        assert (tmp_path / "packs" / "team-rules.rules.json").exists()

    def test_rules_path_is_derived_from_final_pack_name(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.pack.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        assert exit_code == 0
        assert (tmp_path / "packs" / "team.pack.rules.json").exists()

    def test_rules_output_overrides_derived_path(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        rules_output = tmp_path / "generated" / "semantic.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            rules_output_path=str(rules_output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        assert exit_code == 0
        assert rules_output.exists()
        assert not (tmp_path / "packs" / "team.rules.json").exists()

    def test_omitted_optional_lanes_write_no_rules_artifact(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        explicit_rules = tmp_path / "ignored.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            rules_output_path=str(explicit_rules),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response()),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert output.exists()
        assert not explicit_rules.exists()
        assert not (tmp_path / "packs" / "team.rules.json").exists()
        assert "Wrote semantic rules" not in captured.out
        assert "Add a PostToolUse hook" not in captured.out
        assert "Covered by existing linters: none" in captured.out
        assert "Unmapped rules: none" in captured.out

    def test_empty_semantic_lane_does_not_touch_existing_rules_file(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        rules_output = tmp_path / "semantic.json"
        rules_output.write_text("keep me\n", encoding="utf-8")
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            rules_output_path=str(rules_output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=[])),
        )

        assert exit_code == 0
        assert rules_output.read_text(encoding="utf-8") == "keep me\n"

    def test_report_contains_all_lanes_and_wiring_hint(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        report = tmp_path / "reports" / "routing.md"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(
                agent_response(
                    semantic=semantic_rules(),
                    covered_elsewhere=covered_rules(),
                    unmapped=[
                        {
                            "rule": "Monitor latency.",
                            "reason": "Requires runtime telemetry.",
                        }
                    ],
                )
            ),
        )

        captured = capsys.readouterr()
        report_text = report.read_text(encoding="utf-8")
        rules_path = tmp_path / "packs" / "team.rules.json"
        assert exit_code == 0
        assert f"Wrote rule-routing report to {report}" in captured.out
        assert "Covered by existing linters:" not in captured.out
        assert "Monitor latency." not in captured.out
        assert report_text.startswith("# Rule routing report\n")
        assert "## Covered by existing linters" in report_text
        assert "**Mutable class defaults must be annotated.**" in report_text
        assert "## Unmapped rules" in report_text
        assert "**Monitor latency.**: Requires runtime telemetry." in report_text
        assert "## Semantic hook wiring" in report_text
        assert f"--rules {rules_path} --agent claude" in report_text

    def test_report_shows_none_for_empty_covered_and_unmapped_lanes(
        self,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "pack.json"
        report = tmp_path / "routing.md"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(agent_response()),
        )

        report_text = report.read_text(encoding="utf-8")
        assert exit_code == 0
        assert report_text.count("None.") == 2
        assert "Semantic hook wiring" not in report_text

    def test_invalid_semantic_entry_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "pack.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(
                agent_response(
                    semantic=[
                        {
                            "name": "missing-prompt",
                            "match": ["**/*.py"],
                        }
                    ]
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "semantic" in captured.err
        assert "prompt" in captured.err

    def test_invalid_covered_entry_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "pack.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(
                agent_response(
                    covered_elsewhere=[{"rule": "Use Ruff."}],
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert '"coveredElsewhere"' in captured.err

    def test_invalid_pack_and_agent_failure_write_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        write_source(source)

        invalid_output = tmp_path / "invalid.json"
        invalid_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(invalid_output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(pack={"conventions": []})),
        )
        invalid_error = capsys.readouterr().err

        failed_output = tmp_path / "failed.json"
        failed_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(failed_output),
            agent=ExtractAgent.CLAUDE,
            report_path=None,
            runner=FakeRunner(
                AgentRunResult(
                    returncode=2,
                    stdout="",
                    stderr="agent failed",
                )
            ),
        )
        failed_error = capsys.readouterr().err

        assert invalid_code == 1
        assert not invalid_output.exists()
        assert "Invalid extracted reusable-convention package:" in invalid_error
        assert failed_code == 1
        assert not failed_output.exists()
        assert 'Agent CLI "claude" exited with code 2.' in failed_error
        assert "agent failed" in failed_error

    def test_artifact_path_collision_is_rejected_before_write(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "same.json"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            rules_output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "Artifact destinations must be distinct" in captured.err


class TestAgentSelectionAndModel:
    def test_auto_prefers_claude_then_codex(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/{binary}",
        )

        result = select_agent_invocation(ExtractAgent.AUTO)

        assert isinstance(result, Ok)
        assert result.value.agent == "claude"

    def test_missing_agents_return_clear_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda _binary: None,
        )

        result = select_agent_invocation(ExtractAgent.AUTO)

        assert isinstance(result, Err)
        assert "claude" in result.error
        assert "codex" in result.error

    def test_model_and_timeout_reach_real_subprocess_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "pack.json"
        write_source(source)
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/{binary}",
        )
        captured: dict[str, object] = {}

        def fake_run_agent_subprocess(**kwargs):
            captured.update(kwargs)
            return AgentRunResult(
                returncode=0,
                stdout=agent_response(),
                stderr="",
            )

        monkeypatch.setattr(
            "konpy.cli.extract_rules.run_agent_subprocess",
            fake_run_agent_subprocess,
        )

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.CLAUDE,
            report_path=None,
            model="opus",
            timeout=42.0,
        )

        assert exit_code == 0
        assert captured["model"] == "opus"
        assert captured["timeout"] == 42.0
