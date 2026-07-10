from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestTypedRecordsPack:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "typed-records-pack"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "typed-records-pack"),
            "check",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "typed-records-pack-broken"),
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
            _fixture(fixtures_dir, "typed-records-pack-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""

        expected_messages = [
            'Annotation "dict[str, str | int]" on module constant "VALUE"',
            'Annotation "dict[str, object]" on class attribute "Model.metadata"',
            'Annotation "dict[str, Any]" on parameter "payload" of function "handle"',
            'Annotation "dict[str, object]" on return of function "handle"',
            'Annotation "dict[str, Any]" on parameter "items" of function "nested"',
        ]
        for message in expected_messages:
            assert message in stdout

        assert "no-anonymous-record-annotations" in stdout


class TestNoDuplicationPack:
    def test_clean_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "no-duplication-pack"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_clean_fixture_checks_clean(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "no-duplication-pack"),
            "check",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_broken_fixture_validates(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "no-duplication-pack-broken"),
            "validate",
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_broken_fixture_reports_both_duplication_rules(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "no-duplication-pack-broken"),
            "check",
            "--format=json",
            "--max-diagnostics=20",
        )

        # The no-duplication pack ships warning severity (mirroring the
        # clean-only infer proposals), so a violating repo still exits 0.
        assert exit_code == 0
        assert stderr == ""
        assert '"warnings": 4' in stdout

        assert "restrictRepeatedLiterals" in stdout
        assert "at most 2 occurrence(s) of each string literal" in stdout
        assert '"found": "shared-error-message"' in stdout
        assert (
            "Extract the repeated string into a named constant or shared fixture"
            in stdout
        )

        assert "restrictDuplicateFunctions" in stdout
        assert "unique function implementation" in stdout
        assert "duplicate of src/a.py::calculate_a" in stdout
        assert "Extract the shared implementation into one helper" in stdout
