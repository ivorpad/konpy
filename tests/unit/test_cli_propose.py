from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konsistent.cli._hook_findings import HookFinding
from konsistent.cli.agent_runner import AgentInvocation, AgentRunResult, ExtractAgent
from konsistent.cli.app import app
from konsistent.cli.propose import run_propose_command

cli_runner = CliRunner()


def reusable_pack() -> dict[str, object]:
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
    pack: dict[str, object] | None = None,
    unmapped: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps(
        {
            "pack": reusable_pack() if pack is None else pack,
            "unmapped": [] if unmapped is None else unmapped,
        }
    )


def finding(
    *,
    file_path: str = "src/service.py",
    prompt: str = "Verify source files are regular files.",
    reasons: list[str] | None = None,
    agent: str = "claude",
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        agent=agent,
        model="sonnet",
        reasons=["missing matching export"] if reasons is None else reasons,
    )


def write_findings(path: Path, findings: list[HookFinding]) -> None:
    path.write_text(
        "".join(f"{item.model_dump_json(exclude_none=True)}\n" for item in findings),
        encoding="utf-8",
    )


class FakeRunner:
    def __init__(self, responses: AgentRunResult | str | list[AgentRunResult | str]) -> None:
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(self, invocation: AgentInvocation, prompt: str) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class TestRunProposeCommand:
    def test_valid_fake_runner_writes_pack_to_explicit_output_and_prints_unmapped(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        write_findings(
            findings_path,
            [
                finding(
                    file_path="src/service.py",
                    reasons=["missing matching export"],
                )
            ],
        )
        runner = FakeRunner(
            agent_response(
                unmapped=[
                    {
                        "rule": "Semantic review prompt.",
                        "reason": "Requires judgment.",
                    }
                ]
            )
        )

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""
        assert output.exists()
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["conventionSpecVersion"] == "v1"
        assert written["conventions"][0]["name"] == "source-files-are-files"
        assert "Wrote reusable convention proposal to" in captured.out
        assert "Unmapped rules:" in captured.out
        assert "Semantic review prompt." in captured.out
        assert len(runner.calls) == 1
        assert runner.calls[0][0].agent == "claude"
        assert "missing matching export" in runner.calls[0][1]

    def test_default_output_path_is_packs_hook_proposals_under_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        write_findings(findings_path, [finding()])
        monkeypatch.chdir(tmp_path)

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=None,
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response()),
        )

        captured = capsys.readouterr()
        output = tmp_path / "packs" / "hook-proposals.json"
        assert exit_code == 0
        assert captured.err == ""
        assert output.exists()
        assert json.loads(output.read_text(encoding="utf-8"))["conventionSpecVersion"] == "v1"

    def test_report_path_writes_unmapped_report_and_suppresses_inline_unmapped(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        report = tmp_path / "reports" / "unmapped.md"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(
                agent_response(
                    unmapped=[
                        {
                            "rule": "Semantic review prompt.",
                            "reason": "Requires judgment.",
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
        assert str(report) in captured.out
        assert "Unmapped rules:" not in captured.out
        assert "Semantic review prompt." not in captured.out
        report_text = report.read_text(encoding="utf-8")
        assert "# Unmapped rules" in report_text
        assert "Semantic review prompt." in report_text

    def test_missing_findings_file_exits_zero_without_invoking_runner_or_writing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        output = tmp_path / "packs" / "hook-proposal.json"
        runner = FakeRunner(agent_response())

        exit_code = run_propose_command(
            findings_path=str(tmp_path / "missing.jsonl"),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "No fail findings to promote from" in captured.out
        assert captured.err == ""
        assert runner.calls == []
        assert not output.exists()

    def test_only_malformed_findings_warns_and_exits_zero_without_runner(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        findings_path.write_text("{not json\n[]\n", encoding="utf-8")
        runner = FakeRunner(agent_response())

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "malformed JSON" in captured.err
        assert "expected object" in captured.err
        assert "No fail findings to promote from" in captured.out
        assert runner.calls == []
        assert not output.exists()

    def test_malformed_lines_are_warned_but_valid_findings_are_promoted(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        findings_path.write_text(
            "{not json\n"
            f"{finding(file_path='src/valid.py').model_dump_json(exclude_none=True)}\n",
            encoding="utf-8",
        )
        runner = FakeRunner(agent_response())

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "malformed JSON" in captured.err
        assert output.exists()
        assert len(runner.calls) == 1

    def test_invalid_pack_returns_pydantic_issues_and_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(
                agent_response(
                    pack={
                        "conventionSpecVersion": "v1",
                        "conventions": [
                            {
                                "name": "invalid-proposal",
                                "description": "Missing must/mustNot.",
                                "paths": "src/*.py",
                            }
                        ],
                    }
                )
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "Invalid proposed reusable-convention package:" in captured.err
        assert "must" in captured.err or "mustNot" in captured.err

    def test_non_json_agent_response_returns_error_and_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner("I could not produce JSON."),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert not output.exists()
        assert "Agent response did not contain a valid JSON object." in captured.err

    def test_nonzero_agent_result_returns_error_and_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "packs" / "hook-proposal.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
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

    def test_prompt_passed_to_runner_contains_finding_group_evidence(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        write_findings(
            findings_path,
            [
                finding(
                    file_path="src/service.py",
                    prompt="Verify exported class names match filenames.",
                    reasons=["expected Service class was missing"],
                ),
                finding(
                    file_path="src/other_service.py",
                    prompt="Verify exported class names match filenames.",
                    reasons=["expected OtherService class was missing"],
                ),
            ],
        )
        runner = FakeRunner(agent_response())

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(tmp_path / "proposal.json"),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        capsys.readouterr()
        assert exit_code == 0
        assert len(runner.calls) == 1
        prompt = runner.calls[0][1]
        assert "## Finding group 1 (occurrences: 2, agent: claude)" in prompt
        assert "Verify exported class names match filenames." in prompt
        assert "- src/service.py" in prompt
        assert "- src/other_service.py" in prompt
        assert "- expected Service class was missing" in prompt


class TestCliWiring:
    def test_hook_propose_help_exits_zero_and_mentions_default_findings_path(self) -> None:
        result = cli_runner.invoke(app, ["hook-propose", "--help"])

        assert result.exit_code == 0
        assert "hook-propose" in result.output
        assert ".konsistent/hook-findings.jsonl" in result.output
        assert "--timeout" in result.output

    def test_hook_propose_unknown_option_exits_nonzero(self) -> None:
        result = cli_runner.invoke(app, ["hook-propose", "--bogus"])

        assert result.exit_code != 0
        assert "bogus" in result.output or "bogus" in result.stderr
