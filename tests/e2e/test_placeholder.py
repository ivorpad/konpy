from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from konsistent._version import __version__

ANSI_ESCAPE_RE = re.compile(r"\x1b\[")
GITHUB_ANNOTATION_RE = re.compile(r"^::(error|warning) file=.+::.+")
SUMMARY_RE = re.compile(r"Checked \d+ files? in \d+(ms|\.\d+s)\.")


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _combined(stdout: str, stderr: str) -> str:
    return f"{stdout}\n{stderr}"


class TestCliBinary:
    def test_version_command_prints_the_version(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, _stderr = run_cli(fixtures_dir, "version")

        assert exit_code == 0
        assert stdout.strip() == __version__

    def test_version_flag_prints_the_version(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, _stderr = run_cli(fixtures_dir, "--version")

        assert exit_code == 0
        assert stdout.strip() == __version__


class TestEmptyConfigFixture:
    def test_validate_exits_zero(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "empty-config"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_check_exits_zero(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "empty-config"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert SUMMARY_RE.search(stdout) is not None
        assert "No violations found." in stdout

    def test_default_command_no_args_runs_check(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, "empty-config"))

        assert exit_code == 0
        assert stderr == ""
        assert SUMMARY_RE.search(stdout) is not None
        assert "No violations found." in stdout


class TestInvalidConfigFixture:
    def test_validate_exits_one_with_config_error(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "invalid-config"),
            "validate",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert "Invalid config:" in output
        assert "version" in output
        assert "Configuration is valid." not in output

    def test_check_exits_one_with_config_error_before_scan(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "invalid-config"),
            "check",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert "Invalid config:" in output
        assert "version" in output
        assert "Checked" not in stdout
        assert "Found" not in stdout


@pytest.mark.parametrize(
    "name",
    [
        "plugin-system",
        "ai-toolkit",
        "ai-toolkit-with-omissions",
        "function-signatures",
        "class-and-function-contracts",
        "component-library",
        "for-files-array",
        "monorepo-with-negation",
        "case-maps",
        "nth-segment",
        "re-export-from",
        "exclude-files",
        "placeholder-constraints",
        "placeholder-satisfies",
    ],
)
def test_happy_path_fixtures_check_clean(fixtures_dir: Path, run_cli, name: str) -> None:
    exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, name), "check")

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


class TestBrokenFixtures:
    def test_plugin_system_broken_files(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "plugin-system-broken-files"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing required file" in stdout
        assert "README.md" in stdout
        assert "manifest.json" in stdout
        assert 'Missing export "deactivate"' in stdout
        assert 'Missing export constant "plugin_id"' in stdout

    def test_ai_toolkit_broken_exports(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "ai-toolkit-broken-exports"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export "openai"' in stdout
        assert 'Missing export type "OpenaiProviderSettings"' in stdout
        assert 'Missing export type "AnthropicProvider"' in stdout

    def test_ai_toolkit_broken_interfaces(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "ai-toolkit-broken-interfaces"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Interface "OpenaiProvider" must extend "ProviderV1"' in stdout
        assert 'Missing export interface "AnthropicProvider"' in stdout
        assert 'Missing import type "ProviderV1"' in stdout

    def test_ai_toolkit_omissions_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "ai-toolkit-with-omissions-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Interface "OpenaiProvider" must extend "ProviderV1"' in stdout
        assert 'Interface "AnthropicProvider" must extend "ProviderV1"' in stdout

    def test_function_signatures_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "function-signatures-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert (
            'Function "createAuthService" parameter 2 must be of type "AuthLogger"'
            in stdout
        )
        assert (
            'Function "createPaymentsService" must return value of type "PaymentsService"'
            in stdout
        )

    def test_class_and_function_contracts_broken(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "class-and-function-contracts-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Class "CacheAdapter" must extend "BaseAdapter"' in stdout
        assert 'Class "CacheAdapter" must implement "Connectable"' in stdout
        assert 'Missing import type "BaseAdapter"' in stdout
        assert (
            'Function "createDatabaseAdapter" parameter 1 must be of type '
            '"DatabaseAdapterConfig"'
        ) in stdout
        assert (
            'Function "createDatabaseAdapter" must return value of type '
            '"DatabaseAdapter"'
        ) in stdout

    def test_component_library_broken_conditionals(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "component-library-broken-conditionals"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export "describe"' in stdout
        assert 'Missing export constant "meta"' in stdout

    def test_for_files_array_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "for-files-array-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert stdout.count('Missing export "describe"') == 2

    def test_must_block_names_show_block_level_names(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "must-block-names"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "[test-exports]" in stdout
        assert "[story-meta]" in stdout

    def test_monorepo_with_negation_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "monorepo-with-negation-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export "cli"' in stdout
        assert "Found 1 error." in stdout

    def test_case_maps_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "case-maps-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export function "createOpenAIProvider"' in stdout
        assert 'Missing export type "OpenAIProviderConfig"' in stdout
        assert 'Missing export constant "OPENAI_PROVIDER_ID"' in stdout

    def test_re_export_from_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "re-export-from-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export "openai" from ".openai_core"' in stdout
        assert 'Missing export type "OpenaiProvider" from ".openai_core"' in stdout

    def test_exclude_files_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "exclude-files-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export "activate"' in stdout
        assert 'Missing export constant "plugin_id"' in stdout
        assert 'Missing export "describe"' in stdout

    def test_placeholder_constraints_broken(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "placeholder-constraints-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing export function "createOpenaiLanguageModelChat"' in stdout
        assert 'Missing export "AnthropicChatModelConfig"' in stdout


class TestOutputFormats:
    def test_github_format_outputs_annotations_without_summary(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "ai-toolkit-broken-interfaces"),
            "check",
            "--format",
            "github",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "::error file=" in stdout
        assert ",title=provider-interface" in stdout
        assert ",line=" in stdout
        assert "Found" not in stdout
        assert all(GITHUB_ANNOTATION_RE.match(line) for line in stdout.strip().splitlines())

    def test_markdown_format_outputs_tables(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "ai-toolkit-broken-exports"),
            "check",
            "--format",
            "markdown",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "**`packages/" in stdout
        assert "| Line | Severity | Message | Convention |" in stdout
        assert 'Missing export "openai"<br><sub>description: ' in stdout
        assert "Found 3 errors.**" in stdout
        assert ANSI_ESCAPE_RE.search(stdout) is None

    def test_json_format_outputs_expected_diagnostic_shape(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "monorepo-with-negation-broken"),
            "check",
            "--format",
            "json",
        )

        assert exit_code == 1
        assert stderr == ""
        parsed = json.loads(stdout)
        assert parsed["diagnostics"] == [
            {
                "severity": "error",
                "conventionName": "package-barrel-exports",
                "filePath": "packages/cli/src/index.py",
                "predicateName": "export",
                "message": 'Missing export "cli"',
                "description": (
                    "Every package barrel must export a function named after the "
                    "package, except test-utils"
                ),
            }
        ]
        assert parsed["suppressed"] == []
        assert parsed["summary"]["filesChecked"] == 2
        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 0
        assert parsed["summary"]["suppressed"] == 0
        assert isinstance(parsed["summary"]["durationMs"], int | float)
        assert "column" not in parsed["diagnostics"][0]



class TestFlags:
    def test_config_path_works_for_check_and_validate(self, fixtures_dir: Path, run_cli) -> None:
        fixture = _fixture(fixtures_dir, "empty-config")
        config_path = fixture / "konsistent.json"

        exit_code, stdout, stderr = run_cli(
            fixture,
            "check",
            "--config-path",
            str(config_path),
        )
        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

        exit_code, stdout, stderr = run_cli(
            fixtures_dir,
            "validate",
            "--config-path",
            str(config_path),
        )
        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout

    def test_config_path_missing_exits_one(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            fixtures_dir,
            "check",
            "--config-path",
            "/nonexistent/konsistent.json",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert "Could not read config file" in output

    def test_config_package_is_unsupported(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            fixtures_dir,
            "check",
            "--config-package",
            "@scope/config",
        )
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert "--config-package is not supported by the Python port" in output

    def test_no_colors_strips_ansi_from_default_output(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "plugin-system-broken-files"),
            "check",
            "--no-colors",
        )

        assert exit_code == 1
        assert stderr == ""
        assert ANSI_ESCAPE_RE.search(stdout) is None
        assert "Missing required file" in stdout

    def test_max_diagnostics_truncates_displayed_diagnostics(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "class-and-function-contracts-broken"),
            "check",
            "--max-diagnostics",
            "1",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "... and 6 more diagnostics" in stdout
        assert SUMMARY_RE.search(stdout) is not None


class TestWarningsAndSeverity:
    def test_warnings_only_exits_zero_unless_error_on_warnings(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        fixture = _fixture(fixtures_dir, "warnings-only")

        exit_code, stdout, stderr = run_cli(fixture, "check", "--no-colors")
        assert exit_code == 0
        assert stderr == ""
        assert "warning" in stdout
        assert "Missing required file: README.md" in stdout

        exit_code, stdout, stderr = run_cli(fixture, "check", "--error-on-warnings")
        assert exit_code == 1
        assert stderr == ""
        assert "warning" in stdout

    def test_mixed_severity_reports_errors_and_warnings(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "mixed-severity"),
            "check",
            "--no-colors",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "error" in stdout
        assert "warning" in stdout
        assert "Missing required file: index.py" in stdout
        assert "Missing required file: README.md" in stdout
        assert "Found 1 error and 2 warnings." in stdout

    def test_diagnostic_level_error_skips_warning_conventions(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "warnings-only"),
            "check",
            "--diagnostic-level",
            "error",
            "--no-colors",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "warning" not in stdout
        assert "No violations found." in stdout

    @pytest.mark.parametrize("format_", ["github", "json", "markdown"])
    def test_warning_formats_preserve_warning_severity(
        self,
        fixtures_dir: Path,
        run_cli,
        format_: str,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "warnings-only"),
            "check",
            "--format",
            format_,
        )

        assert exit_code == 0
        assert stderr == ""
        assert "warning" in stdout
        assert "Missing required file: README.md" in stdout


class TestDeprecatedFunctionParam:
    def test_validate_exits_zero_and_prints_deprecation_warning(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "deprecated-function-param"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert '"receiveParamOfType" is deprecated' in stdout
        assert "conventions[0].must.exportFunctions[0].receiveParamOfType" in stdout
        assert stdout.rstrip().endswith("Configuration is valid.")

