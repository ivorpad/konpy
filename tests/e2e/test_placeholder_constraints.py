from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestRegexConstraints:
    def test_check_exits_zero_when_matches_filters_and_extract_resolves(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "regex-constraints"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Checked 2 files" in stdout
        assert "No violations found." in stdout

    def test_check_exits_one_with_extract_derived_constant_name(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "regex-constraints-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export constant "open"' in stdout
        assert "Found 1 error" in stdout


class TestPlaceholderSatisfies:
    def test_check_exits_zero_when_conditional_block_is_gated_correctly(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "placeholder-satisfies"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Checked 3 files" in stdout
        assert "No violations found." in stdout

    def test_check_exits_one_when_ai_provider_is_missing_stem_file(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "placeholder-satisfies-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing required file: src/openai-stem.py" in stdout
        assert "Found 1 error" in stdout

