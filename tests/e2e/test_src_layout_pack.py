from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestSrcLayoutPack:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "src-layout-pack"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "src-layout-pack"),
            "check",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "src-layout-pack-broken"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_broken_fixture_reports_violations(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "src-layout-pack-broken"),
            "check",
        )
        assert exit_code == 1
        assert stderr == ""

        expected_messages = [
            "Missing required file: pyproject.toml",
            "Missing required file: __init__.py",
            "Missing paired file: tests/test_service.py",
            "Missing paired file: tests/billing/test_invoice.py",
        ]
        for message in expected_messages:
            assert message in stdout

        expected_conventions = [
            "project-root-uses-src-layout",
            "top-level-src-packages-have-init",
            "top-level-modules-mirror-into-tests",
            "nested-modules-mirror-into-tests",
        ]
        for convention in expected_conventions:
            assert convention in stdout
