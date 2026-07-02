from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from konsistent.cli.app import _preprocess_argv, app
from tests.fake_distribution import install_fake_distribution

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def write_file(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def write_config(tmp_path: Path, conventions: list[dict[str, object]]) -> None:
    write_json(
        tmp_path / "konsistent.json",
        {
            "version": "v1",
            "conventions": conventions,
        },
    )


def make_error_project(tmp_path: Path) -> None:
    (tmp_path / "src" / "index.py").mkdir(parents=True)
    write_config(
        tmp_path,
        [
            {
                "name": "source-files",
                "paths": "src/index.py",
                "must": {"haveType": "file"},
            }
        ],
    )


def make_clean_project(tmp_path: Path) -> None:
    write_file(tmp_path / "src" / "index.py", "VALUE = 1\n")
    write_config(
        tmp_path,
        [
            {
                "name": "source-files",
                "paths": "src/index.py",
                "must": {"haveType": "file"},
            }
        ],
    )


def make_warning_project(tmp_path: Path) -> None:
    (tmp_path / "src" / "index.py").mkdir(parents=True)
    write_config(
        tmp_path,
        [
            {
                "name": "source-should-be-file",
                "severity": "warning",
                "paths": "src/index.py",
                "must": {"haveType": "file"},
            }
        ],
    )


def make_file_level_suppression_project(tmp_path: Path) -> None:
    write_file(
        tmp_path / "src" / "service.py",
        "# konsistent: ignore-file[paired-tests] -- generated\nVALUE = 1\n",
    )
    write_config(
        tmp_path,
        [
            {
                "name": "paired-tests",
                "paths": "src/service.py",
                "must": {"havePairedFile": "tests/test_service.py"},
            }
        ],
    )


def make_unused_suppression_project(tmp_path: Path) -> None:
    write_file(
        tmp_path / "src" / "service.py",
        "# konsistent: ignore[unused-code] -- legacy API\n"
        "def orphaned():\n"
        "    return 1\n",
    )
    write_json(
        tmp_path / "konsistent.json",
        {
            "version": "v1",
            "conventions": [],
            "unusedCode": {},
        },
    )


class TestCheckCommand:
    def test_violation_exits_one_and_prints_default_format(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 1
        assert "src/index.py" in result.output
        assert "error" in result.output
        assert "Expected a file but found a directory" in result.output
        assert "[source-files]" in result.output
        assert "Checked 1 file" in result.output
        assert "Found 1 error." in result.output
        assert "\x1b[" not in result.output

    def test_clean_project_exits_zero_with_no_violations_summary(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_clean_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 0
        assert "Checked 1 file" in result.output
        assert "No violations found." in result.output

    def test_json_format_is_parseable_and_uses_diagnostic_shape(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--format", "json"])

        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert parsed["diagnostics"] == [
            {
                "severity": "error",
                "conventionName": "source-files",
                "filePath": "src/index.py",
                "predicateName": "haveType",
                "message": "Expected a file but found a directory",
            }
        ]
        assert parsed["suppressed"] == []
        assert parsed["summary"]["filesChecked"] == 1
        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 0
        assert parsed["summary"]["suppressed"] == 0
        assert isinstance(parsed["summary"]["durationMs"], int | float)
        assert "line" not in parsed["diagnostics"][0]
        assert "column" not in parsed["diagnostics"][0]

    def test_show_suppressed_prints_suppressed_diagnostics(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_file_level_suppression_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors", "--show-suppressed"])

        assert result.exit_code == 0
        assert "Suppressed diagnostics:" in result.output
        assert "src/service.py" in result.output
        assert "suppressed error" in result.output
        assert "Missing paired file: tests/test_service.py" in result.output
        assert "[paired-tests]" in result.output
        assert "(suppressed by line 1: generated)" in result.output
        assert "No unsuppressed violations found. Suppressed 1 finding." in result.output

    def test_suppressed_error_exits_zero(self, tmp_path: Path, monkeypatch) -> None:
        make_file_level_suppression_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 0
        assert "Missing paired file: tests/test_service.py" not in result.output
        assert "No unsuppressed violations found. Suppressed 1 finding." in result.output

    def test_suppressed_warning_does_not_fail_error_on_warnings(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_unused_suppression_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--error-on-warnings"],
        )

        assert result.exit_code == 0
        assert 'Unused definition "orphaned" is never referenced' not in result.output
        assert "No unsuppressed violations found. Suppressed 1 finding." in result.output

    def test_unused_suppression_warning_fails_with_error_on_warnings(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        write_file(
            tmp_path / "src" / "index.py",
            "# konsistent: ignore[source-files]\nVALUE = 1\n",
        )
        write_config(
            tmp_path,
            [
                {
                    "name": "source-files",
                    "paths": "src/index.py",
                    "must": {"haveType": "file"},
                }
            ],
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--error-on-warnings"],
        )

        assert result.exit_code == 1
        assert 'Unused suppression for "source-files"' in result.output
        assert "Found 1 warning." in result.output

    def test_max_diagnostics_truncates_output_only(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        (tmp_path / "src" / "a.py").mkdir(parents=True)
        (tmp_path / "src" / "b.py").mkdir(parents=True)
        write_config(
            tmp_path,
            [
                {
                    "name": "a-file",
                    "paths": "src/a.py",
                    "must": {"haveType": "file"},
                },
                {
                    "name": "b-file",
                    "paths": "src/b.py",
                    "must": {"haveType": "file"},
                },
            ],
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--max-diagnostics", "1"],
        )

        assert result.exit_code == 1
        assert "src/a.py" in result.output
        assert "src/b.py" not in result.output
        assert "... and 1 more diagnostics" in result.output

    def test_max_diagnostics_truncates_unsuppressed_only_and_preserves_suppressed_count(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        (tmp_path / "src" / "a.py").mkdir(parents=True)
        (tmp_path / "src" / "b.py").mkdir(parents=True)
        write_file(
            tmp_path / "src" / "suppressed.py",
            "# konsistent: ignore-file[paired-tests] -- generated\nVALUE = 1\n",
        )
        write_config(
            tmp_path,
            [
                {
                    "name": "a-file",
                    "paths": "src/a.py",
                    "must": {"haveType": "file"},
                },
                {
                    "name": "b-file",
                    "paths": "src/b.py",
                    "must": {"haveType": "file"},
                },
                {
                    "name": "paired-tests",
                    "paths": "src/suppressed.py",
                    "must": {"havePairedFile": "tests/test_suppressed.py"},
                },
            ],
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--max-diagnostics", "1"],
        )

        assert result.exit_code == 1
        assert "src/a.py" in result.output
        assert "src/b.py" not in result.output
        assert "Suppressed 1 finding." in result.output
        assert "... and 1 more diagnostics" in result.output

    def test_diagnostic_level_error_skips_warning_conventions(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_warning_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--diagnostic-level", "error"],
        )

        assert result.exit_code == 0
        assert "warning" not in result.output
        assert "Expected a file but found a directory" not in result.output
        assert "No violations found." in result.output

    def test_diagnostic_level_error_omits_suppression_hygiene_warnings(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        write_file(
            tmp_path / "src" / "index.py",
            "# konsistent: ignore[source-files]\nVALUE = 1\n",
        )
        write_config(
            tmp_path,
            [
                {
                    "name": "source-files",
                    "paths": "src/index.py",
                    "must": {"haveType": "file"},
                }
            ],
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--diagnostic-level", "error"],
        )

        assert result.exit_code == 0
        assert "Unused suppression" not in result.output
        assert "warning" not in result.output
        assert "No violations found." in result.output

    def test_error_on_warnings_turns_warning_only_run_into_exit_one(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_warning_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--error-on-warnings"],
        )

        assert result.exit_code == 1
        assert "warning" in result.output
        assert "Found 1 warning." in result.output

    def test_github_actions_true_auto_selects_github_format(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        result = runner.invoke(app, ["check"])

        assert result.exit_code == 1
        assert result.output == (
            "::error file=src/index.py,title=source-files::"
            "Expected a file but found a directory\n"
        )
        assert "Checked 1 file" not in result.output


class TestBareInvocationShim:
    def test_inserts_check_for_no_arguments(self) -> None:
        assert _preprocess_argv([]) == ["check"]

    def test_inserts_check_before_root_check_options(self) -> None:
        assert _preprocess_argv(["--format", "json"]) == [
            "check",
            "--format",
            "json",
        ]

    def test_leaves_help_flags_unchanged_and_maps_lone_version_flag(self) -> None:
        assert _preprocess_argv(["--help"]) == ["--help"]
        assert _preprocess_argv(["-h"]) == ["-h"]
        assert _preprocess_argv(["--version"]) == ["version"]

    def test_leaves_known_subcommands_unchanged(self) -> None:
        assert _preprocess_argv(["check", "--format", "json"]) == [
            "check",
            "--format",
            "json",
        ]
        assert _preprocess_argv(["validate"]) == ["validate"]
        assert _preprocess_argv(["version"]) == ["version"]
        assert _preprocess_argv(["help"]) == ["help"]


def plugin_check_source(*, key: str = "requireMarker") -> str:
    return f'''
from konsistent.plugin import PredicatePlugin, create_diagnostic


def handler(*, expected, context, structure, convention_name=None, severity=None):
    source = context.file_system.read_file(context.path)
    if expected in source:
        return []
    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="{key}",
            message=f'Missing marker "{{expected}}"',
            convention_name=convention_name,
            severity=severity,
        )
    ]


plugin = PredicatePlugin(
    key="{key}",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden marker "{{resolved_value}}"',
)
'''


def install_check_plugin(
    *,
    tmp_path: Path,
    monkeypatch,
    distribution_name: str = "konsistent-test-cli-check-plugin",
    import_package: str = "konsistent_test_cli_check_plugin",
    key: str = "requireMarker",
) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name=distribution_name,
        import_package=import_package,
        modules={"rules": plugin_check_source(key=key)},
        entry_points={
            "konsistent.predicates": {
                key: f"{import_package}.rules:plugin",
            }
        },
    )


def write_plugin_config(tmp_path: Path) -> None:
    write_json(
        tmp_path / "konsistent.json",
        {
            "version": "v1",
            "plugins": ["konsistent-test-cli-check-plugin"],
            "conventions": [
                {
                    "name": "plugin-marker",
                    "paths": "src/module.py",
                    "must": {"requireMarker": "PLUGIN_OK"},
                }
            ],
        },
    )


class TestCheckCommandPlugins:
    def test_plugin_violation_appears_in_default_output(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_check_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        write_file(tmp_path / "src" / "module.py", "VALUE = 1\n")
        write_plugin_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 1
        assert "src/module.py" in result.output
        assert 'Missing marker "PLUGIN_OK"' in result.output
        assert "[plugin-marker]" in result.output

    def test_plugin_violation_appears_in_json_output(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_check_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        write_file(tmp_path / "src" / "module.py", "VALUE = 1\n")
        write_plugin_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--format", "json"])

        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert parsed["diagnostics"] == [
            {
                "severity": "error",
                "conventionName": "plugin-marker",
                "filePath": "src/module.py",
                "predicateName": "requireMarker",
                "message": 'Missing marker "PLUGIN_OK"',
            }
        ]
        assert parsed["suppressed"] == []
        assert parsed["summary"]["filesChecked"] == 1
        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 0
        assert parsed["summary"]["suppressed"] == 0
        assert isinstance(parsed["summary"]["durationMs"], int | float)

    def test_plugin_check_exits_zero_when_handler_passes(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_check_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        write_file(tmp_path / "src" / "module.py", "# PLUGIN_OK\n")
        write_plugin_config(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors"])

        assert result.exit_code == 0
        assert "No violations found." in result.output


def test_preprocess_leaves_extract_rules_subcommand_unchanged() -> None:
    assert _preprocess_argv(["extract-rules", "rules.md"]) == [
        "extract-rules",
        "rules.md",
    ]
    assert _preprocess_argv(
        ["extract-rules", "rules.md", "-o", "packs/rules.json"]
    ) == [
        "extract-rules",
        "rules.md",
        "-o",
        "packs/rules.json",
    ]


def test_preprocess_leaves_explain_subcommand_unchanged() -> None:
    assert _preprocess_argv(["explain"]) == ["explain"]
    assert _preprocess_argv(["explain", "--format", "text"]) == [
        "explain",
        "--format",
        "text",
    ]
