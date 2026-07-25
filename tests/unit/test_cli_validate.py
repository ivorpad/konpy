from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from konpy.cli.app import app
from tests.fake_distribution import install_fake_distribution, reusable_convention_package

runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class TestValidateCommand:
    def test_valid_config_exits_zero_and_prints_success(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
        write_json(config_path, {"version": "v1", "conventions": []})

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "Configuration is valid." in result.output

    def test_package_source_config_exits_zero_and_prints_success(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-cli-validate-conventions",
            import_package="konpy_test_cli_validate_conventions",
            package_json=reusable_convention_package("package-must-have-readme"),
        )
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventionSources": {
                    "common": "konpy-test-cli-validate-conventions",
                },
                "conventions": ["common/package-must-have-readme"],
            },
        )

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "Configuration is valid." in result.output

    def test_invalid_config_exits_one_and_prints_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
        write_json(config_path, {"conventions": []})

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 1
        assert f"Invalid config ({config_path}):" in result.output
        assert 'version: Field required (expected "v1")' in result.output

    def test_bad_placeholder_exits_one_before_loading_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
        write_json(config_path, {"version": "v1", "conventions": []})

        result = runner.invoke(
            app,
            [
                "validate",
                "--config-path",
                str(config_path),
                "--placeholder",
                "1bad:value",
            ],
        )

        assert result.exit_code == 1
        assert 'Invalid --placeholder "1bad:value"' in result.output

    def test_placeholder_option_is_applied_during_validation(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
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
                "validate",
                "--config-path",
                str(config_path),
                "--placeholder",
                "providerId:openai",
            ],
        )

        assert result.exit_code == 0
        assert "Configuration is valid." in result.output

    def test_placeholder_validation_error_exits_one(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
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
                "validate",
                "--config-path",
                str(config_path),
                "--placeholder",
                "providerId:openai",
            ],
        )

        assert result.exit_code == 1
        assert '--placeholder "providerId:openai"' in result.output
        assert 'captures "{providerId}" from paths' in result.output

    def test_deprecation_warning_output_precedes_success(self, tmp_path: Path) -> None:
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "paths": "src/*.py",
                        "must": {
                            "declareFunctions": [
                                {"name": "create", "receiveParamOfType": "Config"}
                            ]
                        },
                    }
                ],
            },
        )

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert (
            'Warning: "receiveParamOfType" is deprecated in '
            "conventions[0].must.declareFunctions[0].receiveParamOfType. "
            'Use "receiveParamsOfTypes" instead.'
        ) in result.output
        assert result.output.rstrip().endswith("Configuration is valid.")

    def test_config_package_option_exits_one_with_unsupported_error(self) -> None:
        result = runner.invoke(app, ["validate", "--config-package", "@scope/config"])

        assert result.exit_code == 1
        assert "--config-package is not supported by the Python port." in result.output


def plugin_source(*, key: str = "requireMarker") -> str:
    return f'''
from konpy.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


plugin = PredicatePlugin(
    key="{key}",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden marker "{{resolved_value}}"',
)
'''


def install_validate_plugin(
    *,
    tmp_path: Path,
    monkeypatch,
    distribution_name: str = "konpy-test-cli-validate-plugin",
    import_package: str = "konpy_test_cli_validate_plugin",
    key: str = "requireMarker",
) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name=distribution_name,
        import_package=import_package,
        modules={"rules": plugin_source(key=key)},
        entry_points={
            "konpy.predicates": {
                key: f"{import_package}.rules:plugin",
            }
        },
    )


class TestValidateCommandPlugins:
    def test_plugin_config_exits_zero_when_plugin_is_listed(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_validate_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-cli-validate-plugin"],
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 0
        assert "Configuration is valid." in result.output

    def test_missing_plugin_distribution_exits_one_with_loader_error(
        self,
        tmp_path: Path,
    ) -> None:
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-cli-validate-missing-plugin"],
                "conventions": [],
            },
        )

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 1
        assert (
            'Plugin "konpy-test-cli-validate-missing-plugin": installed Python '
            "distribution not found. Install it or remove it from plugins."
        ) in result.output

    def test_plugin_predicate_is_rejected_without_opt_in(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_validate_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        config_path = tmp_path / "konpy.json"
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )

        result = runner.invoke(app, ["validate", "--config-path", str(config_path)])

        assert result.exit_code == 1
        assert 'unknown predicate key "requireMarker"' in result.output
