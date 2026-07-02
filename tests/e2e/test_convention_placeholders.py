from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _combined(stdout: str, stderr: str) -> str:
    return f"{stdout}\n{stderr}"


class TestConventionPlaceholdersFixture:
    def test_check_exits_zero_when_static_placeholders_feed_must_templates(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "convention-placeholders"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_validate_accepts_the_placeholders_map(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "convention-placeholders"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout


class TestCliPlaceholderOverrideFixture:
    def test_check_fails_with_json_defined_placeholder_value(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "cli-placeholder-override"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing required file" in stdout
        assert "openai_provider.py" in stdout

    def test_check_passes_when_cli_placeholder_overrides_json_value(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "cli-placeholder-override"),
            "check",
            "--placeholder",
            "providerId:anthropic",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_validate_fails_when_cli_placeholder_collides_with_path_capture(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "placeholder-satisfies"),
            "validate",
            "--placeholder",
            "providerId:openai",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert '--placeholder "providerId:openai"' in output
        assert 'captures "{providerId}" from paths' in output

    def test_check_rejects_malformed_placeholder_value(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "convention-placeholders"),
            "check",
            "--placeholder",
            "no-colon-here",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert 'Invalid --placeholder "no-colon-here"' in output


class TestConventionPlaceholdersBrokenFixture:
    def test_validate_fails_when_name_appears_in_paths_and_placeholders(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "convention-placeholders-broken"),
            "validate",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert 'declares placeholder "providerId"' in output
        assert "both in paths" in output
        assert "Pick one." in output

