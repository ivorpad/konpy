from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestM11PredicatesFixture:
    def test_check_exits_zero_when_content_pairing_docstrings_and_annotations_pass(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "content-and-coverage-predicates"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_validate_accepts_m11_predicates(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "content-and-coverage-predicates"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout


class TestM11PredicatesBrokenFixture:
    def test_check_exits_one_with_content_pairing_docstring_and_annotation_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "content-and-coverage-predicates-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'File content must match regex "SPDX-License-Identifier: Apache-2.0"' in stdout
        assert "Missing paired file: tests/test_service.py" in stdout
        assert "Missing module docstring" in stdout
        assert 'Class "Service" must have a docstring' in stdout
        assert 'Function "Service.run" must have a docstring' in stdout
        assert 'Function "create_service" must have a docstring' in stdout
        assert (
            'Function "Service.run" parameter "value" must have a type annotation'
            in stdout
        )
        assert 'Function "Service.run" must have a return type annotation' in stdout
        assert (
            'Function "create_service" parameter "config" must have a type annotation'
            in stdout
        )
        assert 'Function "create_service" must have a return type annotation' in stdout
        assert 'Forbidden content matching regex "TODO"' in stdout
        assert 'Forbidden content matching regex "password\\s*="' in stdout
        assert "content-and-coverage" in stdout
