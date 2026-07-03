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
)
from konpy.config.errors import Err, Ok


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


def agent_response(
    *,
    pack: dict[str, Any] | None = None,
    unmapped: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps(
        {
            "pack": reusable_pack() if pack is None else pack,
            "unmapped": [] if unmapped is None else unmapped,
        }
    )


def write_source(path: Path) -> None:
    path.write_text(
        "# Team rules\n\nEvery source file must be a file.\nUse ruff for formatting.\n",
        encoding="utf-8",
    )


class FakeRunner:
    def __init__(self, response: AgentRunResult | str) -> None:
        self.response = response
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(self, invocation: AgentInvocation, prompt: str) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        return self.response


class TestPromptAssembly:
    def test_prompt_embeds_source_predicates_format_and_mappability_rubric(self) -> None:
        prompt = build_prompt(
            source_text="Use absolute imports only.",
            source_label="rules.md",
            predicates_reference="# Predicates\n\n## importFromParents\n",
        )

        assert "Use absolute imports only." in prompt
        assert "# Predicates" in prompt
        assert "ReusableConventionsPackageV1" in prompt
        assert '"conventionSpecVersion": "v1"' in prompt
        assert "flat object-form" in prompt
        assert "unmapped" in prompt
        assert "Never silently drop a source rule" in prompt
        assert "Do not invent predicate keys" in prompt
        assert "konpy.json" in prompt


class TestJsonExtraction:
    def test_accepts_raw_json_object(self) -> None:
        result = extract_agent_json_object(agent_response())

        assert isinstance(result, Ok)
        assert result.value["pack"]["conventionSpecVersion"] == "v1"

    def test_accepts_fenced_json_object(self) -> None:
        result = extract_agent_json_object(f"```json\n{agent_response()}\n```")

        assert isinstance(result, Ok)
        assert result.value["pack"]["conventionSpecVersion"] == "v1"

    def test_accepts_prose_around_unfenced_json_object(self) -> None:
        result = extract_agent_json_object(f"Here is the proposal:\n{agent_response()}\nDone.")

        assert isinstance(result, Ok)
        assert result.value["unmapped"] == []

    def test_accepts_prose_around_fenced_json_object(self) -> None:
        result = extract_agent_json_object(
            f"Here is the proposal:\n\n```json\n{agent_response()}\n```\nReview it."
        )

        assert isinstance(result, Ok)
        assert result.value["pack"]["conventions"][0]["name"] == "source-files-are-files"

    def test_returns_error_when_no_valid_json_object_exists(self) -> None:
        result = extract_agent_json_object("No JSON here.")

        assert isinstance(result, Err)
        assert result.error == "Agent response did not contain a valid JSON object."


class TestRunExtractRulesCommand:
    def test_valid_fake_runner_writes_pack_to_explicit_output_and_prints_unmapped(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        write_source(source)
        runner = FakeRunner(
            agent_response(
                unmapped=[
                    {
                        "rule": "Use ruff for formatting.",
                        "reason": "Formatting belongs to Ruff.",
                    }
                ]
            )
        )

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""
        assert output.exists()
        assert json.loads(output.read_text(encoding="utf-8")) == reusable_pack()
        assert "Wrote reusable convention proposal to" in captured.out
        assert "Unmapped rules:" in captured.out
        assert "Use ruff for formatting." in captured.out
        assert len(runner.calls) == 1
        assert runner.calls[0][0].agent == "claude"
        assert "Every source file must be a file." in runner.calls[0][1]
        assert "docs/reference/predicates.md" in runner.calls[0][1]

    def test_default_output_path_is_packs_source_stem_under_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "team-rules.md"
        write_source(source)
        monkeypatch.chdir(tmp_path)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=None,
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response()),
        )

        captured = capsys.readouterr()
        output = tmp_path / "packs" / "team-rules.json"
        assert exit_code == 0
        assert captured.err == ""
        assert output.exists()
        assert json.loads(output.read_text(encoding="utf-8"))["conventionSpecVersion"] == "v1"

    def test_report_option_writes_unmapped_report_and_suppresses_detailed_stdout(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        report = tmp_path / "reports" / "unmapped.md"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(
                agent_response(
                    unmapped=[
                        {
                            "rule": "Use ruff for formatting.",
                            "reason": "Formatting belongs to Ruff.",
                        }
                    ]
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert output.exists()
        assert report.exists()
        assert "Wrote unmapped-rules report to" in captured.out
        assert "Unmapped rules:" not in captured.out
        assert "Use ruff for formatting." not in captured.out
        assert "# Unmapped rules" in report.read_text(encoding="utf-8")
        assert "Use ruff for formatting." in report.read_text(encoding="utf-8")

    def test_invalid_or_missing_json_returns_error_and_writes_no_output(
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
            runner=FakeRunner("I could not produce JSON."),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "Agent response did not contain a valid JSON object." in captured.err

    def test_invalid_pack_returns_pydantic_issues_and_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        report = tmp_path / "unmapped.md"
        write_source(source)

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(agent_response(pack={"conventions": []})),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert not report.exists()
        assert "Invalid extracted reusable-convention package:" in captured.err
        assert "conventionSpecVersion" in captured.err

    def test_invalid_unmapped_contract_returns_error_and_writes_nothing(
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
                json.dumps(
                    {
                        "pack": reusable_pack(),
                        "unmapped": [{"rule": "Use ruff."}],
                    }
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert '"unmapped" must be a list of objects' in captured.err

    def test_nonzero_agent_result_returns_error_and_writes_nothing(
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
            agent=ExtractAgent.CLAUDE,
            report_path=None,
            runner=FakeRunner(
                AgentRunResult(
                    returncode=2,
                    stdout="agent stdout",
                    stderr="agent stderr",
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert 'Agent CLI "claude" exited with code 2.' in captured.err
        assert "agent stderr" in captured.err

    def test_unreadable_source_file_returns_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        output = tmp_path / "packs" / "team.json"

        exit_code = run_extract_rules_command(
            source_file=str(tmp_path / "missing.md"),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response()),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "Could not read source file:" in captured.err


class TestAgentSelection:
    def test_auto_selects_claude_before_codex_when_both_are_available(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_which(binary: str) -> str | None:
            if binary in {"claude", "codex"}:
                return f"/fake/bin/{binary}"
            return None

        monkeypatch.setattr("konpy.cli.agent_runner.shutil.which", fake_which)

        result = select_agent_invocation(ExtractAgent.AUTO)

        assert isinstance(result, Ok)
        assert result.value.agent == "claude"
        assert result.value.executable == "/fake/bin/claude"
        assert result.value.prefix_args == ("-p",)

    def test_auto_selects_codex_when_claude_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_which(binary: str) -> str | None:
            if binary == "codex":
                return "/fake/bin/codex"
            return None

        monkeypatch.setattr("konpy.cli.agent_runner.shutil.which", fake_which)

        result = select_agent_invocation(ExtractAgent.AUTO)

        assert isinstance(result, Ok)
        assert result.value.agent == "codex"
        assert result.value.prefix_args == ("exec",)

    def test_auto_missing_error_names_both_supported_binaries(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("konpy.cli.agent_runner.shutil.which", lambda _binary: None)

        result = select_agent_invocation(ExtractAgent.AUTO)

        assert isinstance(result, Err)
        assert "claude" in result.error
        assert "codex" in result.error

    def test_explicit_missing_agent_names_requested_binary(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("konpy.cli.agent_runner.shutil.which", lambda _binary: None)

        result = select_agent_invocation(ExtractAgent.CODEX)

        assert isinstance(result, Err)
        assert result.error == 'Agent CLI "codex" not found on PATH.'

    def test_explicit_agent_uses_plan_invocation_forms(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/bin/{binary}",
        )

        claude = select_agent_invocation(ExtractAgent.CLAUDE)
        codex = select_agent_invocation(ExtractAgent.CODEX)

        assert isinstance(claude, Ok)
        assert isinstance(codex, Ok)
        assert claude.value.prefix_args == ("-p",)
        assert codex.value.prefix_args == ("exec",)


class TestModelThreading:
    def test_default_model_reaches_run_agent_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "rules.md"
        output = tmp_path / "packs" / "team.json"
        write_source(source)

        monkeypatch.setattr(
            "konpy.cli.agent_runner.shutil.which",
            lambda binary: f"/fake/bin/{binary}",
        )
        captured: dict[str, object] = {}

        def fake_run_agent_subprocess(*, invocation, prompt, model=None, **kwargs):
            captured["model"] = model
            return AgentRunResult(returncode=0, stdout=agent_response(), stderr="")

        monkeypatch.setattr(
            "konpy.cli.extract_rules.run_agent_subprocess",
            fake_run_agent_subprocess,
        )

        exit_code = run_extract_rules_command(
            source_file=str(source),
            output_path=str(output),
            agent=ExtractAgent.CLAUDE,
            report_path=None,
        )

        assert exit_code == 0
        assert captured["model"] == "sonnet"
