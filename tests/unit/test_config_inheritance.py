from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from konsistent.config.errors import Err, Ok
from konsistent.config.inheritance import collect_config_plugins, resolve_config_inheritance
from konsistent.config.plugin_loader import load_plugin_registry
from tests.fake_distribution import install_fake_distribution, raw_config_package


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def convention_names(conventions: list[Any]) -> list[str | None]:
    names: list[str | None] = []
    for convention in conventions:
        if isinstance(convention, dict):
            names.append(convention.get("name"))
        else:
            names.append(None)
    return names


class TestResolveConfigInheritance:
    def test_merges_parent_then_child_and_strips_load_only_keys(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"

        write_json(
            base_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "base-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "disable": [],
            "conventions": [
                {
                    "name": "child-rule",
                    "paths": "packages/{packageName}",
                    "must": {"haveFiles": ["pyproject.toml"]},
                }
            ],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert "extends" not in result.value
        assert "disable" not in result.value
        assert convention_names(result.value["conventions"]) == ["base-rule", "child-rule"]

    def test_disable_does_not_remove_same_file_convention(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"

        write_json(
            base_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "package-shape",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "disable": ["package-shape"],
            "conventions": [
                {
                    "name": "package-shape",
                    "paths": "packages/{packageName}",
                    "must": {"haveFiles": ["pyproject.toml"]},
                }
            ],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert convention_names(result.value["conventions"]) == ["package-shape"]
        assert result.value["conventions"][0]["must"] == {"haveFiles": ["pyproject.toml"]}

    def test_disable_does_not_remove_string_or_use_refs(self, tmp_path: Path) -> None:
        base_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"

        write_json(
            base_path,
            {
                "version": "v1",
                "conventions": [
                    "common/foo",
                    {
                        "use": "common/bar",
                        "paths": "packages/{packageName}",
                    },
                ],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "disable": ["foo", "bar"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value["conventions"] == [
            "common/foo",
            {
                "use": "common/bar",
                "paths": "packages/{packageName}",
            },
        ]

    def test_inherited_relative_convention_sources_are_rewritten_absolute(
        self,
        tmp_path: Path,
    ) -> None:
        shared_dir = tmp_path / "shared"
        base_path = shared_dir / "base.json"
        root_path = tmp_path / "konsistent.json"

        write_json(
            base_path,
            {
                "version": "v1",
                "conventionSources": {"common": "./local-conventions.json"},
                "conventions": [],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./shared/base.json"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value["conventionSources"] == {
            "common": str((shared_dir / "local-conventions.json").resolve())
        }

    def test_missing_parent_path_returns_clear_error(self, tmp_path: Path) -> None:
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["./missing.json"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "./missing.json" from {root_path.resolve()}: could not read file at '
            f"{(tmp_path / 'missing.json').resolve()}."
        )

    def test_package_extends_loads_full_raw_config_and_merges(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-base-config",
            import_package="konsistent_test_base_config",
            package_json={
                "version": "v1",
                "kebabToPascalMap": {"openai": "OpenAI"},
                "conventions": [
                    {
                        "name": "base-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-base-config"],
            "conventions": [
                {
                    "name": "child-rule",
                    "paths": "packages/{packageName}",
                    "must": {"haveFiles": ["pyproject.toml"]},
                }
            ],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value["kebabToPascalMap"] == {"openai": "OpenAI"}
        assert convention_names(result.value["conventions"]) == ["base-rule", "child-rule"]

    def test_package_extends_loads_dist_info_konsistent_json_fallback(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-dist-info-base-config",
            import_package="konsistent_test_dist_info_base_config",
            dist_info_json=raw_config_package("from-dist-info"),
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-dist-info-base-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert convention_names(result.value["conventions"]) == ["from-dist-info"]

    def test_package_parent_can_declare_package_convention_sources(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-source-parent-config",
            import_package="konsistent_test_source_parent_config",
            package_json={
                "version": "v1",
                "conventionSources": {"common": "konsistent-test-common-conventions"},
                "conventions": [],
            },
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-source-parent-config"],
            "conventions": ["common/package-must-have-readme"],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value["conventionSources"] == {
            "common": "konsistent-test-common-conventions"
        }
        assert result.value["conventions"] == ["common/package-must-have-readme"]

    def test_package_parent_rejects_relative_convention_sources(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-relative-source-parent-config",
            import_package="konsistent_test_relative_source_parent_config",
            package_json={
                "version": "v1",
                "conventionSources": {"common": "./local-conventions.json"},
                "conventions": [],
            },
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-relative-source-parent-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "konsistent-test-relative-source-parent-config" from '
            f"{root_path.resolve()}: package config at package "
            "konsistent_test_relative_source_parent_config/konsistent.json declares relative "
            'conventionSources["common"] = "./local-conventions.json". Relative '
            "conventionSources are not supported inside package-loaded configs; use an "
            "absolute path or an installed package name."
        )

    def test_package_loaded_config_rejects_relative_local_path_extends(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-relative-extends-parent-config",
            import_package="konsistent_test_relative_extends_parent_config",
            package_json={
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-relative-extends-parent-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            'Config extends "./base.json" from package '
            "konsistent_test_relative_extends_parent_config/konsistent.json: relative "
            "local-path extends are not supported inside package-loaded configs. Use an "
            "absolute path or an installed package name."
        )

    def test_package_inheritance_cycle_error_names_the_cycle(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-cycle-a-config",
            import_package="konsistent_test_cycle_a_config",
            package_json={
                "version": "v1",
                "extends": ["konsistent-test-cycle-b-config"],
                "conventions": [],
            },
        )
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-cycle-b-config",
            import_package="konsistent_test_cycle_b_config",
            package_json={
                "version": "v1",
                "extends": ["konsistent-test-cycle-a-config"],
                "conventions": [],
            },
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-cycle-a-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            "Config inheritance cycle detected: package "
            "konsistent_test_cycle_a_config/konsistent.json -> package "
            "konsistent_test_cycle_b_config/konsistent.json -> package "
            "konsistent_test_cycle_a_config/konsistent.json."
        )

    def test_package_extends_not_installed_returns_clear_error(self, tmp_path: Path) -> None:
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-definitely-not-installed-parent"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "konsistent-test-definitely-not-installed-parent" from '
            f"{root_path.resolve()}: installed Python distribution not found. Install it or "
            "use a local path in extends."
        )

    def test_package_extends_malformed_json_returns_clear_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-malformed-parent-config",
            import_package="konsistent_test_malformed_parent_config",
            package_json_text="{ not json",
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-malformed-parent-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "konsistent-test-malformed-parent-config" from '
            f"{root_path.resolve()}: malformed JSON at package "
            "konsistent_test_malformed_parent_config/konsistent.json."
        )

    def test_package_extends_invalid_config_returns_clear_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-invalid-parent-config",
            import_package="konsistent_test_invalid_parent_config",
            package_json={"conventions": []},
        )
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["konsistent-test-invalid-parent-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert (
            f'Config extends "konsistent-test-invalid-parent-config" from '
            f"{root_path.resolve()}: invalid config at package "
            "konsistent_test_invalid_parent_config/konsistent.json:"
        ) in result.error
        assert "version" in result.error

    def test_invalid_package_extends_name_returns_clear_error(self, tmp_path: Path) -> None:
        root_path = tmp_path / "konsistent.json"
        root_raw = {
            "version": "v1",
            "extends": ["@scope/base-config"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "@scope/base-config" from {root_path.resolve()}: invalid Python '
            "distribution name. Bare package sources must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
        )


def inheritance_plugin_source(*, key: str = "requireMarker") -> str:
    return f'''
from konsistent.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


plugin = PredicatePlugin(
    key="{key}",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden marker "{{resolved_value}}"',
)
'''


def install_inheritance_plugin(
    *,
    tmp_path: Path,
    monkeypatch,
    distribution_name: str,
    import_package: str,
    key: str,
) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name=distribution_name,
        import_package=import_package,
        modules={"rules": inheritance_plugin_source(key=key)},
        entry_points={
            "konsistent.predicates": {
                key: f"{import_package}.rules:plugin",
            }
        },
    )


class TestResolveConfigInheritancePlugins:
    def test_collect_config_plugins_reads_parent_then_child(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-parent-plugin"],
                "conventions": [],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "plugins": ["konsistent-test-child-plugin"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = collect_config_plugins(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value == [
            "konsistent-test-parent-plugin",
            "konsistent-test-child-plugin",
        ]

    def test_collect_config_plugins_dedupes_by_normalized_distribution_name(
        self,
        tmp_path: Path,
    ) -> None:
        parent_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-repeat-plugin"],
                "conventions": [],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "plugins": ["konsistent_test_repeat_plugin"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = collect_config_plugins(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value == ["konsistent-test-repeat-plugin"]

    def test_resolve_inheritance_merges_plugins_parent_then_child(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-parent-plugin"],
                "conventions": [],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "plugins": ["konsistent-test-child-plugin"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Ok)
        assert result.value["plugins"] == [
            "konsistent-test-parent-plugin",
            "konsistent-test-child-plugin",
        ]

    def test_parent_plugin_predicate_validates_when_parent_declares_plugin(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_inheritance_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konsistent-test-inheritance-plugin",
            import_package="konsistent_test_inheritance_plugin",
            key="requireMarker",
        )
        parent_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-inheritance-plugin"],
                "conventions": [
                    {
                        "name": "parent-plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        plugins_result = collect_config_plugins(raw=root_raw, config_path=root_path)
        assert isinstance(plugins_result, Ok)
        registry_result = load_plugin_registry(plugins=plugins_result.value)
        assert isinstance(registry_result, Ok)

        result = resolve_config_inheritance(
            raw=root_raw,
            config_path=root_path,
            predicate_registry=registry_result.value,
        )

        assert isinstance(result, Ok)
        assert result.value["plugins"] == ["konsistent-test-inheritance-plugin"]
        assert result.value["conventions"][0]["must"] == {"requireMarker": "PLUGIN_OK"}

    def test_parent_plugin_predicate_fails_without_registry(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        root_path = tmp_path / "konsistent.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konsistent-test-inheritance-plugin"],
                "conventions": [
                    {
                        "name": "parent-plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )
        root_raw = {
            "version": "v1",
            "extends": ["./base.json"],
            "conventions": [],
        }
        write_json(root_path, root_raw)

        result = resolve_config_inheritance(raw=root_raw, config_path=root_path)

        assert isinstance(result, Err)
        assert 'unknown predicate key "requireMarker"' in result.error
