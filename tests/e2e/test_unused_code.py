from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestUnusedCodeCleanFixture:
    def test_exits_zero_when_everything_used_or_silent(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "unused-code"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_config_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, _stderr = run_cli(
            _fixture(fixtures_dir, "unused-code"),
            "validate",
        )

        assert exit_code == 0
        assert "Configuration is valid." in stdout


class TestUnusedCodeBrokenFixture:
    def test_reports_dead_and_test_only_as_warnings(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "unused-code-broken"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert 'Unused definition "orphaned" is never referenced' in stdout
        assert 'Definition "Service.tested_only" is only referenced by tests' in stdout
        assert "Found 2 warnings." in stdout

    def test_error_on_warnings_exits_one(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, _stdout, _stderr = run_cli(
            _fixture(fixtures_dir, "unused-code-broken"),
            "check",
            "--error-on-warnings",
        )

        assert exit_code == 1

    def test_diagnostic_level_error_skips_warning_severity(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, _stderr = run_cli(
            _fixture(fixtures_dir, "unused-code-broken"),
            "check",
            "--diagnostic-level",
            "error",
        )

        assert exit_code == 0
        assert "No violations found." in stdout
