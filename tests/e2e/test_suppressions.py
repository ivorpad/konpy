from __future__ import annotations

import json
from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestInlineSuppressionsFixture:
    def test_suppressed_findings_are_counted_but_hidden_by_default(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions"),
            "check",
            "--no-colors",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No unsuppressed violations found. Suppressed 4 findings." in stdout
        assert "Suppressed diagnostics:" not in stdout
        assert "Missing paired file: tests/test_service.py" not in stdout
        assert 'Forbidden content matching regex "DEBUG_ONLY"' not in stdout
        assert 'Function "orphaned" must have a docstring' not in stdout
        assert 'Unused definition "orphaned" is never referenced' not in stdout

    def test_show_suppressed_lists_suppressed_findings_and_reasons(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions"),
            "check",
            "--no-colors",
            "--show-suppressed",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Suppressed diagnostics:" in stdout
        assert "src/service.py" in stdout
        assert "src/debug.py" in stdout
        assert "src/legacy.py" in stdout
        assert "Missing paired file: tests/test_service.py" in stdout
        assert 'Forbidden content matching regex "DEBUG_ONLY"' in stdout
        assert 'Function "orphaned" must have a docstring' in stdout
        assert 'Unused definition "orphaned" is never referenced' in stdout
        assert "(suppressed by line 1: generated module has no direct test)" in stdout
        assert "(suppressed by line 1: debug fixture is intentionally checked in)" in stdout
        assert "(suppressed by line 1: approved legacy hook)" in stdout

    def test_json_output_includes_suppressed_array(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions"),
            "check",
            "--format",
            "json",
        )

        assert exit_code == 0
        assert stderr == ""
        parsed = json.loads(stdout)
        assert parsed["diagnostics"] == []
        assert parsed["summary"]["filesChecked"] == 3
        assert parsed["summary"]["errors"] == 0
        assert parsed["summary"]["warnings"] == 0
        assert parsed["summary"]["suppressed"] == 4
        assert len(parsed["suppressed"]) == 4

        suppressed_by_rule = {
            item["conventionName"]: item for item in parsed["suppressed"]
        }
        assert set(suppressed_by_rule) == {
            "docstrings",
            "paired-tests",
            "no-debug-content",
            "unused-code",
        }
        assert suppressed_by_rule["docstrings"]["suppressedBy"] == {
            "kind": "ignore",
            "filePath": "src/legacy.py",
            "line": 1,
            "reason": "approved legacy hook",
        }
        assert suppressed_by_rule["unused-code"]["suppressedBy"] == {
            "kind": "ignore",
            "filePath": "src/legacy.py",
            "line": 1,
            "reason": "approved legacy hook",
        }
        assert suppressed_by_rule["paired-tests"]["suppressedBy"] == {
            "kind": "ignore-file",
            "filePath": "src/service.py",
            "line": 1,
            "reason": "generated module has no direct test",
        }
        assert suppressed_by_rule["no-debug-content"]["suppressedBy"] == {
            "kind": "ignore-file",
            "filePath": "src/debug.py",
            "line": 1,
            "reason": "debug fixture is intentionally checked in",
        }


class TestInlineSuppressionsStaleFixture:
    def test_stale_suppression_is_reported_as_warning_by_default(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions-stale"),
            "check",
            "--no-colors",
        )

        assert exit_code == 0
        assert stderr == ""
        assert 'Unused suppression for "source-files"' in stdout
        assert "Found 1 warning." in stdout

    def test_stale_suppression_fails_with_error_on_warnings(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions-stale"),
            "check",
            "--no-colors",
            "--error-on-warnings",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Unused suppression for "source-files"' in stdout
        assert "Found 1 warning." in stdout

    def test_diagnostic_level_error_omits_stale_suppression_warning(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "inline-suppressions-stale"),
            "check",
            "--no-colors",
            "--diagnostic-level",
            "error",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Unused suppression" not in stdout
        assert "No violations found." in stdout
