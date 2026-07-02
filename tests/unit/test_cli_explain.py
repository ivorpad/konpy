from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from konsistent.cli.app import app
from tests.fake_distribution import install_fake_distribution, reusable_convention_package

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class TestExplainCommand:
    def test_default_format_is_markdown(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "must-have-readme",
                        "paths": "packages/*",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "## Conventions" in result.output

    def test_format_text_flag_produces_plain_text(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "must-have-readme",
                        "paths": "packages/*",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )

        result = runner.invoke(
            app, ["explain", "--config-path", str(config_path), "--format", "text"]
        )

        assert result.exit_code == 0
        assert "##" not in result.output
        assert "`" not in result.output
        assert "must-have-readme" in result.output

    def test_config_path_option_loads_alternate_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "alt.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {"name": "alt-rule", "paths": "src/*.py", "must": {"haveType": "file"}}
                ],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "alt-rule" in result.output

    def test_missing_config_file_exits_one_with_error(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "nope.json"

        result = runner.invoke(app, ["explain", "--config-path", str(missing_path)])

        assert result.exit_code == 1
        assert "Could not read config file" in result.output

    def test_invalid_config_exits_one_and_prints_validation_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(config_path, {"conventions": []})

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 1
        assert "Invalid config:" in result.output
        assert "version" in result.output

    def test_config_package_option_exits_one_with_unsupported_error(self) -> None:
        result = runner.invoke(app, ["explain", "--config-package", "@scope/config"])

        assert result.exit_code == 1
        assert "--config-package is not supported by the Python port." in result.output

    def test_bad_placeholder_exits_one_before_loading_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(config_path, {"version": "v1", "conventions": []})

        result = runner.invoke(
            app,
            [
                "explain",
                "--config-path",
                str(config_path),
                "--placeholder",
                "1bad:value",
            ],
        )

        assert result.exit_code == 1
        assert 'Invalid --placeholder "1bad:value"' in result.output

    def test_placeholder_option_is_applied_and_render_succeeds(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "packages/openai/src/index.py",
                        "must": {"export": ["${providerId}"]},
                    }
                ],
            },
        )

        result = runner.invoke(
            app,
            [
                "explain",
                "--config-path",
                str(config_path),
                "--placeholder",
                "providerId:openai",
            ],
        )

        assert result.exit_code == 0
        assert "openai" in result.output

    def test_placeholder_conflict_with_path_capture_exits_one(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "packages/{providerId}",
                        "must": {"export": ["${providerId}"]},
                    }
                ],
            },
        )

        result = runner.invoke(
            app,
            [
                "explain",
                "--config-path",
                str(config_path),
                "--placeholder",
                "providerId:openai",
            ],
        )

        assert result.exit_code == 1
        assert '--placeholder "providerId:openai"' in result.output
        assert 'captures "{providerId}" from paths' in result.output

    def test_extends_resolution_is_reflected_in_output(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.json"
        write_json(
            base_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "base-rule",
                        "paths": "src/*.py",
                        "must": {"haveType": "file"},
                    }
                ],
            },
        )
        child_path = tmp_path / "child.json"
        write_json(
            child_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(child_path)])

        assert result.exit_code == 0
        assert "base-rule" in result.output
        assert "src/*.py" in result.output

    def test_disable_removes_inherited_convention_from_output(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.json"
        write_json(
            base_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "base-rule",
                        "paths": "src/*.py",
                        "must": {"haveType": "file"},
                    }
                ],
            },
        )
        child_path = tmp_path / "child.json"
        write_json(
            child_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "disable": ["base-rule"],
                "conventions": [],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(child_path)])

        assert result.exit_code == 0
        assert "base-rule" not in result.output

    def test_convention_source_pack_reference_is_reflected_in_output(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-cli-explain-conventions",
            import_package="konsistent_test_cli_explain_conventions",
            package_json=reusable_convention_package("package-must-have-readme"),
        )
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventionSources": {
                    "common": "konsistent-test-cli-explain-conventions",
                },
                "conventions": ["common/package-must-have-readme"],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "package-must-have-readme" in result.output
        assert "README.md" in result.output

    def test_plugin_predicate_key_is_rendered_generically(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        plugin_source = '''
from konsistent.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


plugin = PredicatePlugin(
    key="requireMarker",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden marker "{resolved_value}"',
)
'''
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-cli-explain-plugin",
            import_package="konsistent_test_cli_explain_plugin",
            modules={"rules": plugin_source},
            entry_points={
                "konsistent.predicates": {
                    "requireMarker": "konsistent_test_cli_explain_plugin.rules:plugin",
                }
            },
        )
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-cli-explain-plugin"],
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "requireMarker" in result.output
        assert "PLUGIN_OK" in result.output

    def test_unusedCode_present_renders_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(
            config_path,
            {"version": "v1", "conventions": [], "unusedCode": {}},
        )

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "## Unused code" in result.output

    def test_no_unusedCode_key_omits_section(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(config_path, {"version": "v1", "conventions": []})

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "Unused code" not in result.output

    def test_help_command_lists_explain(self) -> None:
        result = runner.invoke(app, ["help"])

        assert "explain" in result.output

    def test_bare_explain_invocation_is_not_swallowed_by_default_check_shim(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "konsistent.json"
        write_json(config_path, {"version": "v1", "conventions": []})

        result = runner.invoke(app, ["explain", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "## Conventions" in result.output
