from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestPythonBestPracticesPack:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-broken"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_broken_fixture_reports_representative_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""

        expected_messages = [
            "Barrel file must not contain declarations",
            "Forbidden content matching regex",
            "Forbidden import from current directory",
            "Missing paired file: tests/test_service.py",
            'Function "_private_helper" must have a docstring',
            'Function "_private_helper" parameter "value" must have a type annotation',
            'Function "_private_helper" must have a return type annotation',
            'Class "PaymentProcessor" must have a docstring',
            'Function "PaymentProcessor.run" must have a docstring',
            'Function "PaymentProcessor.run" parameter "amount" must have a type annotation',
            'Function "PaymentProcessor.run" must have a return type annotation',
            'Missing export class "PaymentService"',
            'Missing export constant "RETRY_LIMIT"',
        ]
        for message in expected_messages:
            assert message in stdout

        expected_conventions = [
            "init-files-are-barrels",
            "no-underscore-exports",
            "absolute-imports-only",
            "paired-test-files",
            "docstrings-on-public-api",
            "annotated-public-functions",
            "class-name-matches-filename",
            "exported-constants-are-upper-case",
        ]
        for convention in expected_conventions:
            assert convention in stdout


class TestPythonBestPracticesPackExtended:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-extended"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-extended"),
            "check",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-extended-broken"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_broken_fixture_reports_violations(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "python-best-practices-pack-extended-broken"),
            "check",
        )
        assert exit_code == 1
        assert stderr == ""

        expected_messages = [
            "Forbidden content matching regex",
            "File content must match regex",
            "Missing module docstring",
            "Missing required file: README.md",
        ]
        for message in expected_messages:
            assert message in stdout

        expected_conventions = [
            "no-todo-comments",
            "public-api-modules-declare-all",
            "package-inits-have-docstrings",
            "component-packages-have-readme",
        ]
        for convention in expected_conventions:
            assert convention in stdout
