"""Tests for `konpy init` (starter-config generation) and `konpy init --agents`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import app
from konpy.cli.init import INIT_TEMPLATE
from konpy.config.errors import Ok
from konpy.config.loader import load_config, load_config_runtime

runner = CliRunner()


class TestInitCommand:
    def test_writes_starter_config_and_prints_next_steps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == INIT_TEMPLATE
        assert "Wrote konpy.json" in result.output
        assert "konpy check" in result.output
        assert "konpy docs" in result.output

    def test_refuses_to_overwrite_an_existing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        existing = '{"version": "v1", "conventions": []}\n'
        (tmp_path / "konpy.json").write_text(existing, encoding="utf-8")

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 1
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == existing
        assert "already exists" in result.output

    def test_starter_config_passes_the_real_config_loader(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = load_config(config_path=tmp_path / "konpy.json")

        assert isinstance(result, Ok)
        assert result.value.version == "v1"
        assert result.value.unusedCode is not None

        names = [convention.name for convention in result.value.conventions]
        assert len(names) == 18
        for expected in (
            "project-root-uses-src-layout",
            "init-files-are-barrels",
            "max-module-length",
            "no-typing-any",
            "annotated-public-functions",
            "docstrings-on-public-api",
            "tests-mirror-package-modules",
            "no-duplicate-functions",
        ):
            assert expected in names

    def test_starter_ratchets_are_warnings_the_rest_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = load_config(config_path=tmp_path / "konpy.json")

        assert isinstance(result, Ok)
        warning_names = {
            convention.name
            for convention in result.value.conventions
            if convention.severity == "warning"
        }
        assert warning_names == {
            "no-todo-comments",
            "no-repeated-string-literals",
            "no-duplicate-functions",
        }


class TestInitAgentsCommand:
    def test_scaffolds_all_four_artifacts_in_a_fresh_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init", "--agents"])

        assert result.exit_code == 0
        assert (tmp_path / "konpy.json").is_file()
        assert (tmp_path / "AGENTS.md").is_file()
        assert (tmp_path / ".claude" / "settings.json").is_file()
        assert not (tmp_path / ".gitignore").exists()
        assert "skipped (no .gitignore)" in result.output

        loaded = load_config_runtime(config_path=tmp_path / "konpy.json")
        assert isinstance(loaded, Ok)
        assert loaded.value.config.verify is not None
        step_names = {step.name for step in loaded.value.config.verify.steps}
        assert step_names == {"konpy-validate", "konpy-check"}
        by_name = {step.name: step.run for step in loaded.value.config.verify.steps}
        assert by_name["konpy-validate"] == ["konpy", "validate"]
        assert by_name["konpy-check"] == ["konpy", "check"]

        agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "<!-- konpy:generated-guidance:start -->" in agents_md
        assert "<!-- konpy:generated-guidance:end -->" in agents_md
        assert "generated from konpy.json" in agents_md
        assert "project-root-uses-src-layout" in agents_md

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        post_command = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert "konpy gate" in pre_command
        assert "konpy review" in post_command
        assert "--log .konpy/hook-findings.jsonl" in post_command

    def test_existing_konpy_json_is_skipped_but_other_artifacts_are_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])  # pre-existing plain (non-agents) config
        original = (tmp_path / "konpy.json").read_text(encoding="utf-8")

        result = runner.invoke(app, ["init", "--agents"])

        assert result.exit_code == 0
        assert "skipped (exists): konpy.json" in result.output
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == original
        assert (tmp_path / "AGENTS.md").is_file()
        assert (tmp_path / ".claude" / "settings.json").is_file()

    def test_everything_already_existing_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "konpy.json").write_text('{"version": "v1", "conventions": []}\n')
        (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n")
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n")

        result = runner.invoke(app, ["init", "--agents"])

        assert result.exit_code == 1
        assert "skipped (exists): konpy.json" in result.output
        assert "skipped (exists): AGENTS.md" in result.output
        assert "skipped (exists): .claude/settings.json" in result.output
        assert "skipped (no .gitignore)" in result.output

    def test_claude_settings_skip_points_at_the_hooks_guide(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("{}\n")

        result = runner.invoke(app, ["init", "--agents"])

        assert "docs/guides/claude-code-hook.md" in result.output

    def test_gitignore_gains_a_konpy_entry_when_missing_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

        result = runner.invoke(app, ["init", "--agents"])

        assert result.exit_code == 0
        assert "Updated .gitignore" in result.output
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n.konpy/\n"

    def test_gitignore_already_containing_the_entry_is_left_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        original = "node_modules/\n.konpy/\n"
        (tmp_path / ".gitignore").write_text(original, encoding="utf-8")

        result = runner.invoke(app, ["init", "--agents"])

        assert "skipped (already present): .gitignore" in result.output
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == original

    def test_missing_gitignore_is_not_created(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init", "--agents"])

        assert not (tmp_path / ".gitignore").exists()
        assert "skipped (no .gitignore)" in result.output

    def test_unrenderable_existing_config_skips_agents_md_but_keeps_going(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "konpy.json").write_text("not valid json", encoding="utf-8")

        result = runner.invoke(app, ["init", "--agents"])

        assert result.exit_code == 0
        assert "skipped (exists): konpy.json" in result.output
        assert "skipped (could not render guidance from konpy.json): AGENTS.md" in result.output
        assert not (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".claude" / "settings.json").is_file()

    def test_plain_init_does_not_scaffold_agent_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == INIT_TEMPLATE
        assert not (tmp_path / "AGENTS.md").exists()
        assert not (tmp_path / ".claude").exists()
