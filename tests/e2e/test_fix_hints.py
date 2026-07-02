from __future__ import annotations

import json
from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestFixHintsFixture:
    def test_check_exits_zero_when_service_is_fully_documented(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "fix-hints-and-descriptions"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_validate_accepts_convention_level_description_and_hint(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "fix-hints-and-descriptions"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout


class TestFixHintsBrokenFixture:
    def test_json_diagnostics_surface_description_hint_expected_found_fix_hint(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "fix-hints-and-descriptions-broken"),
            "check",
            "--format",
            "json",
        )

        assert exit_code == 1
        assert stderr == ""
        parsed = json.loads(stdout)
        diagnostics = parsed["diagnostics"]
        assert len(diagnostics) == 8

        # Every diagnostic inherits the convention's description and hint,
        # even though none of the touched predicates set those fields.
        for item in diagnostics:
            assert item["description"] == (
                "Service modules must be paired, documented, annotated, and "
                "exported correctly."
            )
            assert item["hint"] == (
                "Run the service generator template if you are starting a new service."
            )

        paired_file = next(d for d in diagnostics if d["predicateName"] == "havePairedFile")
        assert paired_file["expected"] == "tests/test_service.py"
        assert "fixHint" in paired_file
        assert "found" not in paired_file

        extend_violation = next(
            d for d in diagnostics if d["predicateName"] == "exportClasses"
        )
        assert extend_violation["expected"] == "BaseService"
        assert extend_violation["found"] == "OtherBase"

        docstring_violation = next(
            d
            for d in diagnostics
            if d["predicateName"] == "haveDocstrings" and d["message"] == "Missing module docstring"
        )
        assert docstring_violation["expected"] == "module docstring"
        assert "found" not in docstring_violation

        annotation_violation = next(
            d
            for d in diagnostics
            if d["predicateName"] == "annotateFunctions"
            and "return type annotation" in d["message"]
        )
        assert annotation_violation["expected"] == "return type annotation"

    def test_default_format_appends_hint_suffix_line(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "fix-hints-and-descriptions-broken"),
            "check",
            "--format",
            "default",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing paired file: tests/test_service.py" in stdout
        assert "-> description: Service modules must be paired" in stdout
        assert "fix: Create the paired file at" in stdout

    def test_markdown_format_appends_hint_suffix_to_message_cell(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "fix-hints-and-descriptions-broken"),
            "check",
            "--format",
            "markdown",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "<br><sub>description: Service modules must be paired" in stdout
        assert "fix: Create the paired file at" in stdout
