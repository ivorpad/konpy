from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestHexagonalArchitecturePack:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "hexagonal-architecture-pack"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "hexagonal-architecture-pack"),
            "check",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "hexagonal-architecture-pack-broken"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_broken_fixture_reports_violations(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "hexagonal-architecture-pack-broken"),
            "check",
        )
        assert exit_code == 1
        assert stderr == ""

        expected_messages = [
            "Forbidden content matching regex",
            "File content must match regex",
            "Missing paired file: tests/use_cases/test_create_order.py",
        ]
        for message in expected_messages:
            assert message in stdout

        expected_conventions = [
            "domain-does-not-import-adapters-or-infrastructure",
            "ports-are-protocols-or-abcs",
            "adapters-export-adapter-suffix",
            "use-cases-paired-with-tests",
        ]
        for convention in expected_conventions:
            assert convention in stdout
