from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli._hook_findings import HookFinding
from konpy.cli.agent_runner import AgentInvocation, AgentRunResult, ExtractAgent
from konpy.cli.app import app
from konpy.cli.propose import run_propose_command

cli_runner = CliRunner()
_MISSING = object()


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


def semantic_rules() -> list[dict[str, object]]:
    return [
        {
            "name": "check-service-behavior",
            "prompt": "Verify that each service method performs its documented behavior.",
            "match": ["src/**/*_service.py"],
            "source": "Service methods must implement their documented behavior.",
        }
    ]


def agent_response(
    *,
    pack: dict[str, object] | None = None,
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


def finding(
    *,
    file_path: str = "src/service.py",
    prompt: str = "Verify source files are regular files.",
    reasons: list[str] | None = None,
    agent: str = "claude",
    rule: str | None = None,
) -> HookFinding:
    return HookFinding(
        filePath=file_path,
        prompt=prompt,
        rule=rule,
        agent=agent,
        model="sonnet",
        reasons=["missing matching export"] if reasons is None else reasons,
    )


def write_findings(path: Path, findings: list[HookFinding]) -> None:
    path.write_text(
        "".join(
            f"{item.model_dump_json(exclude_none=True)}\n" for item in findings
        ),
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


class TestRunProposeCommand:
    def test_four_lane_response_writes_pack_rules_and_inline_report(
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
                    semantic=semantic_rules(),
                    covered_elsewhere=[
                        {
                            "rule": "Disallow mutable defaults.",
                            "tool": "ruff B006",
                            "note": "Ruff checks function argument defaults.",
                        }
                    ],
                    unmapped=[
                        {
                            "rule": "Rotate on-call reviewers.",
                            "reason": "This is process guidance.",
                        }
                    ],
                )
            ),
        )

        captured = capsys.readouterr()
        rules_path = tmp_path / "packs" / "hook-proposal.rules.json"
        assert exit_code == 0
        assert output.exists()
        assert rules_path.exists()
        assert json.loads(rules_path.read_text(encoding="utf-8")) == {
            "semanticRulesSpecVersion": "v1",
            "rules": semantic_rules(),
        }
        assert f"Wrote semantic rules to {rules_path}" in captured.out
        assert "Covered by existing linters:" in captured.out
        assert "ruff B006" in captured.out
        assert "Unmapped rules:" in captured.out
        assert "Rotate on-call reviewers." in captured.out
        assert f"--rules {rules_path} --agent claude" in captured.out

    def test_default_paths_write_hook_proposals_artifacts(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        write_findings(findings_path, [finding()])
        monkeypatch.chdir(tmp_path)

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=None,
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        assert exit_code == 0
        assert (tmp_path / "packs" / "hook-proposals.json").exists()
        assert (tmp_path / "packs" / "hook-proposals.rules.json").exists()

    def test_explicit_rules_output_is_used(
        self,
        tmp_path: Path,
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        rules_output = tmp_path / "semantic" / "rules.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            rules_output_path=str(rules_output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(agent_response(semantic=semantic_rules())),
        )

        assert exit_code == 0
        assert rules_output.exists()
        assert not (tmp_path / "pack.rules.json").exists()

    def test_old_two_lane_response_remains_accepted(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        explicit_rules = tmp_path / "ignored-rules.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
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
        assert "Wrote semantic rules" not in captured.out
        assert "Covered by existing linters: none" in captured.out
        assert "Unmapped rules: none" in captured.out

    def test_report_is_lane_aware_and_suppresses_inline_details(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        report = tmp_path / "reports" / "routing.md"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=str(report),
            runner=FakeRunner(
                agent_response(
                    semantic=semantic_rules(),
                    covered_elsewhere=[
                        {
                            "rule": "Use typed exceptions.",
                            "tool": "mypy",
                        }
                    ],
                    unmapped=[
                        {
                            "rule": "Monitor services.",
                            "reason": "Requires runtime telemetry.",
                        }
                    ],
                )
            ),
        )

        captured = capsys.readouterr()
        report_text = report.read_text(encoding="utf-8")
        assert exit_code == 0
        assert f"Wrote rule-routing report to {report}" in captured.out
        assert "Use typed exceptions." not in captured.out
        assert "Monitor services." not in captured.out
        assert report_text.startswith("# Rule routing report\n")
        assert "## Covered by existing linters" in report_text
        assert "**Use typed exceptions.**: mypy" in report_text
        assert "## Unmapped rules" in report_text
        assert "**Monitor services.**: Requires runtime telemetry." in report_text
        assert "## Semantic hook wiring" in report_text

    def test_invalid_semantic_response_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
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

    def test_invalid_covered_response_writes_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        write_findings(findings_path, [finding()])

        exit_code = run_propose_command(
            findings_path=str(findings_path),
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

    def test_missing_or_invalid_findings_do_not_invoke_agent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        output = tmp_path / "pack.json"
        missing_runner = FakeRunner(agent_response())

        missing_code = run_propose_command(
            findings_path=str(tmp_path / "missing.jsonl"),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=missing_runner,
        )
        missing_output = capsys.readouterr()

        invalid_path = tmp_path / "invalid.jsonl"
        invalid_path.write_text("{not json\n", encoding="utf-8")
        invalid_runner = FakeRunner(agent_response())
        invalid_code = run_propose_command(
            findings_path=str(invalid_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=invalid_runner,
        )
        invalid_output = capsys.readouterr()

        assert missing_code == 0
        assert missing_runner.calls == []
        assert "No fail findings to promote" in missing_output.out
        assert invalid_code == 0
        assert invalid_runner.calls == []
        assert "malformed JSON" in invalid_output.err

    def test_prompt_receives_grouped_rule_specific_evidence(
        self,
        tmp_path: Path,
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        output = tmp_path / "pack.json"
        prompt = "Verify exported class names match filenames."
        write_findings(
            findings_path,
            [
                finding(
                    file_path="src/a.py",
                    prompt=prompt,
                    rule="matching-export",
                    reasons=["A export is missing."],
                ),
                finding(
                    file_path="src/b.py",
                    prompt=prompt,
                    rule="matching-export",
                    reasons=["B export is missing."],
                ),
            ],
        )
        runner = FakeRunner(agent_response())

        exit_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=runner,
        )

        assert exit_code == 0
        assert len(runner.calls) == 1
        proposal_prompt = runner.calls[0][1]
        assert "occurrences: 2" in proposal_prompt
        assert prompt in proposal_prompt
        assert "- src/a.py" in proposal_prompt
        assert "- src/b.py" in proposal_prompt
        assert "- A export is missing." in proposal_prompt

    def test_invalid_pack_and_agent_failure_write_nothing(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        findings_path = tmp_path / "findings.jsonl"
        write_findings(findings_path, [finding()])

        invalid_output = tmp_path / "invalid.json"
        invalid_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(invalid_output),
            agent=ExtractAgent.AUTO,
            report_path=None,
            runner=FakeRunner(
                agent_response(
                    pack={
                        "conventionSpecVersion": "v1",
                        "conventions": [
                            {
                                "name": "invalid",
                                "description": "Missing must.",
                                "paths": "src/*.py",
                            }
                        ],
                    }
                )
            ),
        )
        invalid_error = capsys.readouterr().err

        failed_output = tmp_path / "failed.json"
        failed_code = run_propose_command(
            findings_path=str(findings_path),
            output_path=str(failed_output),
            agent=ExtractAgent.CLAUDE,
            report_path=None,
            runner=FakeRunner(
                AgentRunResult(
                    returncode=3,
                    stdout="",
                    stderr="agent failed",
                )
            ),
        )
        failed_error = capsys.readouterr().err

        assert invalid_code == 1
        assert not invalid_output.exists()
        assert "Invalid proposed reusable-convention package:" in invalid_error
        assert failed_code == 1
        assert not failed_output.exists()
        assert 'Agent CLI "claude" exited with code 3.' in failed_error


class TestCliWiring:
    def test_help_mentions_rules_output(self) -> None:
        result = cli_runner.invoke(app, ["hook-propose", "--help"])

        assert result.exit_code == 0
        assert "--rules-output" in result.output
        assert ".konpy/hook-findings.jsonl" in result.output

    def test_unknown_option_is_rejected(self) -> None:
        result = cli_runner.invoke(app, ["hook-propose", "--bogus"])

        assert result.exit_code != 0
