from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestExplainGuidanceFixture:
    def test_markdown_output_renders_name_description_hint_and_severity(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "## Conventions" in stdout
        assert "`documented-service`" in stdout
        assert "Service modules must be paired and documented." in stdout
        assert "hint: Create the paired test file next to the service module." in stdout
        assert "severity: `error`" in stdout

    def test_unnamed_convention_gets_a_generated_name(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "must-not-match-content" in stdout

    def test_unused_code_section_reflects_resolved_config(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "## Unused code" in stdout
        assert "legacy_shim" in stdout
        # Framework defaults/presets are resolved, not just user-provided keys.
        assert "conftest.py" in stdout

    def test_output_ends_with_suppression_consent_note(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "## Suppressions" in stdout
        assert "docs/reference/suppressions.md" in stdout
        assert "without explicit human approval" in stdout

    def test_text_format_has_no_markdown_syntax(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance"),
            "explain",
            "--format",
            "text",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "documented-service" in stdout
        assert not any(line.startswith("#") for line in stdout.splitlines())


class TestExplainGuidanceExtendsFixture:
    def test_inherited_convention_is_rendered(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance-extends"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "package-must-have-readme" in stdout
        assert "packages/{packageName}" in stdout

    def test_disabled_inherited_convention_is_absent(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "explain-guidance-extends"),
            "explain",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "package-must-have-license" not in stdout
