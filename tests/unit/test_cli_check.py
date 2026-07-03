from __future__ import annotations

import json
import subprocess
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


def make_two_file_error_project(tmp_path: Path) -> None:
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


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class TestDiffScopedCheck:
    def test_check_files_flag_restricts_output_to_named_file(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_two_file_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors", "--files", "src/a.py"])

        assert result.exit_code == 1
        assert "src/a.py" in result.output
        assert "src/b.py" not in result.output
        assert "Checked 1 file" in result.output

    def test_check_files_flag_repeated_occurrences(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_two_file_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--files", "src/a.py", "--files", "src/b.py"],
        )

        assert result.exit_code == 1
        assert "src/a.py" in result.output
        assert "src/b.py" in result.output
        assert "Checked 2 file" in result.output

    def test_check_files_flag_single_occurrence_space_list(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_two_file_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        repeated_argv = ["check", "--no-colors", "--files", "src/a.py", "--files", "src/b.py"]
        space_list_argv = ["check", "--no-colors", "--files", "src/a.py", "src/b.py"]

        repeated = runner.invoke(app, repeated_argv)
        # `_preprocess_argv` (invoked by `main()` in real usage) is what
        # expands the single space-separated occurrence into repeated
        # `--files` tokens before Click ever sees them.
        space_list = runner.invoke(app, _preprocess_argv(space_list_argv))

        assert space_list.exit_code == repeated.exit_code == 1
        assert space_list.output == repeated.output

    def test_check_files_and_changed_together_errors(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_two_file_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--files", "src/a.py", "--changed"],
        )

        assert result.exit_code == 1
        assert "--files" in result.output
        assert "--changed" in result.output

    def test_check_changed_flag_uses_git_scope(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        # Two independent, single-file conventions: only the one whose
        # matched file (src/a.py) intersects the git-changed scope is
        # selected. The b-file convention's matched set (src/b.py) has zero
        # intersection with the changed scope, so it is skipped entirely --
        # unlike a shared-glob convention, where any overlap pulls in the
        # whole matched set.
        write_config(
            tmp_path,
            [
                {
                    "name": "a-file-must-export-process",
                    "paths": "src/a.py",
                    "must": {"export": ["process"]},
                },
                {
                    "name": "b-file-must-export-process",
                    "paths": "src/b.py",
                    "must": {"export": ["process"]},
                },
            ],
        )
        write_file(tmp_path / "src" / "a.py", "VALUE = 1\n")
        write_file(tmp_path / "src" / "b.py", "VALUE = 1\n")
        _init_git_repo(tmp_path)
        # Both files violate their convention from the start; only src/a.py
        # is touched after the commit, so `--changed` should scope the run
        # to the a-file convention alone and leave src/b.py's (also-real)
        # violation unreported.
        write_file(tmp_path / "src" / "a.py", "VALUE = 2\n")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors", "--changed"])

        assert result.exit_code == 1
        assert "src/a.py" in result.output
        assert "src/b.py" not in result.output
        assert "Checked 1 file" in result.output

    def test_check_changed_flag_no_changes_is_clean_and_zero_exit(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_clean_project(tmp_path)
        _init_git_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--no-colors", "--changed"])

        assert result.exit_code == 0
        assert "Checked 0 file" in result.output

    def test_check_files_flag_nonexistent_path_is_silently_a_no_op(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_two_file_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app,
            ["check", "--no-colors", "--files", "does-not-exist.py"],
        )

        assert result.exit_code == 0
        assert "Checked 0 file" in result.output


class TestPreprocessArgvFilesExpansion:
    def test_preprocess_expands_files_space_separated_before_next_flag(self) -> None:
        assert _preprocess_argv(["check", "--files", "a.py", "b.py", "--format", "json"]) == [
            "check",
            "--files",
            "a.py",
            "--files",
            "b.py",
            "--format",
            "json",
        ]

    def test_preprocess_files_expansion_stops_at_next_flag_token(self) -> None:
        assert _preprocess_argv(["check", "--files", "a.py", "--no-colors"]) == [
            "check",
            "--files",
            "a.py",
            "--no-colors",
        ]

    def test_preprocess_files_equals_form_untouched(self) -> None:
        assert _preprocess_argv(["check", "--files=a.py"]) == ["check", "--files=a.py"]

    def test_preprocess_bare_files_flag_with_no_values_left_for_click_to_reject(
        self,
    ) -> None:
        assert _preprocess_argv(["check", "--files"]) == ["check", "--files"]

        result = runner.invoke(app, ["check", "--files"])

        assert result.exit_code != 0


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

    def test_json_format_max_diagnostics_truncates_array_but_not_summary_counts(
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
            ["check", "--format", "json", "--max-diagnostics", "1"],
        )

        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert len(parsed["diagnostics"]) == 1
        assert parsed["summary"]["errors"] == 2
        assert parsed["truncation"] == {"shown": 1, "omitted": 1}
        assert "... and" not in result.output

    def test_json_format_truncation_key_present_and_zero_when_not_truncated(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        make_error_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["check", "--format", "json"])

        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert parsed["truncation"] == {"shown": 1, "omitted": 0}

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


def test_preprocess_leaves_infer_subcommand_unchanged() -> None:
    assert _preprocess_argv(["infer"]) == ["infer"]
    assert _preprocess_argv(["infer", "--min-confidence", "0.5"]) == [
        "infer",
        "--min-confidence",
        "0.5",
    ]


def test_preprocess_leaves_explain_subcommand_unchanged() -> None:
    assert _preprocess_argv(["explain"]) == ["explain"]
    assert _preprocess_argv(["explain", "--format", "text"]) == [
        "explain",
        "--format",
        "text",
    ]
