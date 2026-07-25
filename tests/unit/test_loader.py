from __future__ import annotations

import json
from pathlib import Path

from konpy.config.errors import Err, Ok
from konpy.config.loader import (
    CONFIG_FILENAME,
    apply_cli_placeholders,
    load_config,
    load_config_runtime,
    path_declared_names,
)
from konpy.config.schema import ConventionV1
from tests.fake_distribution import (
    install_fake_distribution,
    raw_config_package,
    reusable_convention_package,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def unsupported_config_package_error() -> str:
    return (
        "--config-package is not supported by the Python port. Use --config-path with a "
        "local konpy.json file."
    )


class TestPathDeclaredNames:
    def test_collects_names_from_single_path(self) -> None:
        assert path_declared_names("packages/{providerId}/src/{name:segments(2)}") == {
            "providerId",
            "name",
        }

    def test_collects_names_from_path_array(self) -> None:
        assert path_declared_names(["src/{a}", "lib/{b:matches(^x$)}"]) == {"a", "b"}


class TestApplyCliPlaceholders:
    def test_merges_cli_placeholders_into_every_convention(self) -> None:
        conventions = [
            ConventionV1.model_validate(
                {
                    "paths": "packages/openai/src/index.py",
                    "placeholders": {"providerId": "openai"},
                    "must": {"export": ["${providerId}"]},
                }
            ),
            ConventionV1.model_validate(
                {
                    "paths": "packages/anthropic/src/index.py",
                    "must": {"export": ["${providerId}"]},
                }
            ),
        ]

        result = apply_cli_placeholders(
            conventions=conventions,
            identifiers=["a", "b"],
            cli_placeholders={"providerId": "anthropic"},
        )

        assert isinstance(result, Ok)
        assert result.value[0].placeholders == {"providerId": "anthropic"}
        assert result.value[1].placeholders == {"providerId": "anthropic"}

    def test_rejects_collisions_with_path_captured_names_and_collects_all(self) -> None:
        conventions = [
            ConventionV1.model_validate(
                {"paths": "packages/{providerId}", "must": {"haveType": "directory"}}
            ),
            ConventionV1.model_validate(
                {"paths": "plugins/{providerId}", "must": {"haveType": "directory"}}
            ),
        ]

        result = apply_cli_placeholders(
            conventions=conventions,
            identifiers=["first", "second"],
            cli_placeholders={"providerId": "openai"},
        )

        assert isinstance(result, Err)
        assert result.error == (
            '--placeholder "providerId:openai" conflicts with convention "first" which '
            'captures "{providerId}" from paths. CLI placeholders may only override values '
            "in placeholders, not path-determined ones.\n"
            '--placeholder "providerId:openai" conflicts with convention "second" which '
            'captures "{providerId}" from paths. CLI placeholders may only override values '
            "in placeholders, not path-determined ones."
        )


class TestLoadConfig:
    def test_loads_valid_empty_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(config_path, {"version": "v1", "conventions": []})

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.version == "v1"
        assert result.value.conventions == []

    def test_loads_default_config_from_current_working_directory(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        write_json(tmp_path / CONFIG_FILENAME, {"version": "v1", "conventions": []})
        monkeypatch.chdir(tmp_path)

        result = load_config()

        assert isinstance(result, Ok)
        assert result.value.version == "v1"

    def test_returns_error_for_invalid_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {"conventions": [{"paths": ["src/*.py"], "must": {"unknownPredicate": ["foo"]}}]},
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error.startswith(f"Invalid config ({config_path}):\n")
        assert "version" in result.error
        assert '(expected "v1")' in result.error

    def test_returns_error_when_config_file_does_not_exist(self, tmp_path: Path) -> None:
        config_path = tmp_path / "missing.json"

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == (
            f"Could not read config file: {config_path}\n"
            "Run 'konpy init' to create one, or 'konpy docs configuration' "
            "for the config reference."
        )

    def test_returns_error_for_invalid_json(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        config_path.write_text("{ not json", encoding="utf-8")

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == f"Invalid JSON in config file: {config_path}"

    def test_resolves_local_convention_sources_and_expands_string_refs(
        self,
        tmp_path: Path,
    ) -> None:
        write_json(
            tmp_path / "local-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "package-must-have-readme",
                        "description": "Every package must contain README.",
                        "paths": ["packages/{packageName}"],
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventionSources": {"common": "./local-conventions.json"},
                "conventions": ["common/package-must-have-readme"],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.conventions[0].name == "package-must-have-readme"
        assert result.value.conventions[0].paths == ["packages/{packageName}"]

    def test_resolves_package_convention_sources_and_expands_string_refs(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-loader-conventions",
            import_package="konpy_test_loader_conventions",
            package_json=reusable_convention_package("package-must-have-readme"),
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventionSources": {"common": "konpy-test-loader-conventions"},
                "conventions": ["common/package-must-have-readme"],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.conventions[0].name == "package-must-have-readme"
        assert result.value.conventions[0].paths == "packages/{packageName}"

    def test_merges_cli_placeholders_into_every_convention_placeholders_map(
        self,
        tmp_path: Path,
    ) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "openai-provider-barrel",
                        "paths": "packages/openai/src/index.py",
                        "placeholders": {"providerId": "openai"},
                        "must": {"haveFiles": ["${providerId}-provider.py"]},
                    }
                ],
            },
        )

        result = load_config(
            config_path=config_path,
            cli_placeholders={"providerId": "anthropic"},
        )

        assert isinstance(result, Ok)
        assert result.value.conventions[0].placeholders == {"providerId": "anthropic"}

    def test_rejects_cli_placeholder_that_collides_with_path_captured_name(
        self,
        tmp_path: Path,
    ) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "ai-provider-stems",
                        "paths": "packages/{providerId}",
                        "must": [{"must": {"haveFiles": ["src/index.py"]}}],
                    }
                ],
            },
        )

        result = load_config(
            config_path=config_path,
            cli_placeholders={"providerId": "openai"},
        )

        assert isinstance(result, Err)
        assert '--placeholder "providerId:openai"' in result.error
        assert 'captures "{providerId}" from paths' in result.error

    def test_returns_placeholder_validation_errors_after_expansion(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "broken",
                        "paths": "src/{x}",
                        "must": {"haveFiles": ["${missing}.py"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'references "${missing}"' in result.error

    def test_surfaces_source_resolver_errors(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "conventionSources": {"common": "./missing.json"},
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'Convention source "common"' in result.error
        assert "could not read file" in result.error

    def test_errors_when_both_config_path_and_config_package_are_passed(self) -> None:
        result = load_config(
            config_path="/some/path/konpy.json",
            config_package="@scope/some-pkg",
        )

        assert isinstance(result, Err)
        assert result.error == (
            "Cannot use --config-path and --config-package together. Pass only one."
        )

    def test_config_package_is_explicitly_unsupported(self) -> None:
        result = load_config(config_package="@scope/root-config")

        assert isinstance(result, Err)
        assert result.error == unsupported_config_package_error()

    def test_config_package_path_form_is_still_unsupported(self) -> None:
        result = load_config(config_package="./local-config")

        assert isinstance(result, Err)
        assert result.error == unsupported_config_package_error()

    def test_config_package_empty_string_is_still_unsupported(self) -> None:
        result = load_config(config_package="")

        assert isinstance(result, Err)
        assert result.error == unsupported_config_package_error()


class TestLoadConfigInheritance:
    def test_no_extends_config_does_not_expose_load_only_fields(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(config_path, {"version": "v1", "conventions": []})

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert not hasattr(result.value, "extends")
        assert not hasattr(result.value, "disable")

    def test_parent_and_child_deep_merge_non_convention_fields(self, tmp_path: Path) -> None:
        write_json(
            tmp_path / "parent-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "unused-parent-source",
                        "description": "Unused parent source.",
                        "paths": "packages/{packageName}",
                        "must": {"haveType": "directory"},
                    }
                ],
            },
        )
        write_json(
            tmp_path / "child-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "unused-child-source",
                        "description": "Unused child source.",
                        "paths": "packages/{packageName}",
                        "must": {"haveType": "directory"},
                    }
                ],
            },
        )
        parent_path = tmp_path / "base.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "kebabToPascalMap": {"openai": "OpenAI"},
                "conventionSources": {"parent": "./parent-conventions.json"},
                "unusedCode": {
                    "include": ["src/**/*.py"],
                    "allow": ["legacy_helper"],
                },
                "conventions": [
                    {
                        "name": "parent-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "kebabToCamelMap": {"openai": "openAI"},
                "conventionSources": {"child": "./child-conventions.json"},
                "unusedCode": {
                    "include": ["lib/**/*.py"],
                    "severity": "error",
                },
                "conventions": [
                    {
                        "name": "child-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["pyproject.toml"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.kebabToPascalMap == {"openai": "OpenAI"}
        assert result.value.kebabToCamelMap == {"openai": "openAI"}
        assert result.value.conventionSources == {
            "parent": str((tmp_path / "parent-conventions.json").resolve()),
            "child": "./child-conventions.json",
        }
        assert result.value.unusedCode is not None
        assert result.value.unusedCode.include == ["lib/**/*.py"]
        assert result.value.unusedCode.allow == ["legacy_helper"]
        assert result.value.unusedCode.severity == "error"
        assert [convention.name for convention in result.value.conventions] == [
            "parent-rule",
            "child-rule",
        ]

    def test_multiple_parents_merge_left_to_right_before_child(self, tmp_path: Path) -> None:
        parent_a_path = tmp_path / "parent-a.json"
        parent_b_path = tmp_path / "parent-b.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            parent_a_path,
            {
                "version": "v1",
                "kebabToPascalMap": {"provider": "ProviderA"},
                "conventions": [
                    {
                        "name": "shared-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["A.md"]},
                    },
                    {
                        "name": "only-a",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["only-a.md"]},
                    },
                ],
            },
        )
        write_json(
            parent_b_path,
            {
                "version": "v1",
                "kebabToPascalMap": {"provider": "ProviderB"},
                "conventions": [
                    {
                        "name": "shared-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["B.md"]},
                    }
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./parent-a.json", "./parent-b.json"],
                "conventions": [
                    {
                        "name": "child-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["child.md"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.kebabToPascalMap == {"provider": "ProviderB"}
        assert [convention.name for convention in result.value.conventions] == [
            "shared-rule",
            "only-a",
            "child-rule",
        ]
        assert result.value.conventions[0].must is not None
        assert result.value.conventions[0].must.haveFiles == ["B.md"]

    def test_child_convention_with_same_raw_name_replaces_inherited_in_place(
        self,
        tmp_path: Path,
    ) -> None:
        parent_path = tmp_path / "base.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            parent_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "package-shape",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    },
                    {
                        "name": "second-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["second.md"]},
                    },
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [
                    {
                        "name": "package-shape",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md", "pyproject.toml"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == [
            "package-shape",
            "second-rule",
        ]
        assert result.value.conventions[0].must is not None
        assert result.value.conventions[0].must.haveFiles == ["README.md", "pyproject.toml"]

    def test_child_disable_removes_inherited_named_convention(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "base.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            parent_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "keep-me",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    },
                    {
                        "name": "drop-me",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["LICENSE"]},
                    },
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "disable": ["drop-me"],
                "conventions": [
                    {
                        "name": "child-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["pyproject.toml"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == [
            "keep-me",
            "child-rule",
        ]

    def test_intermediate_parent_disable_removes_ancestor_convention(self, tmp_path: Path) -> None:
        grandparent_path = tmp_path / "grandparent.json"
        parent_path = tmp_path / "parent.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            grandparent_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "grandparent-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    },
                    {
                        "name": "drop-at-parent",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["LICENSE"]},
                    },
                ],
            },
        )
        write_json(
            parent_path,
            {
                "version": "v1",
                "extends": ["./grandparent.json"],
                "disable": ["drop-at-parent"],
                "conventions": [
                    {
                        "name": "parent-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["pyproject.toml"]},
                    }
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./parent.json"],
                "conventions": [
                    {
                        "name": "child-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["py.typed"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == [
            "grandparent-rule",
            "parent-rule",
            "child-rule",
        ]

    def test_recursive_extends_loads_all_ancestors(self, tmp_path: Path) -> None:
        grandparent_path = tmp_path / "grandparent.json"
        parent_path = tmp_path / "parent.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            grandparent_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "grandparent-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        write_json(
            parent_path,
            {
                "version": "v1",
                "extends": ["./grandparent.json"],
                "conventions": [
                    {
                        "name": "parent-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["pyproject.toml"]},
                    }
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./parent.json"],
                "conventions": [
                    {
                        "name": "child-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["py.typed"]},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == [
            "grandparent-rule",
            "parent-rule",
            "child-rule",
        ]

    def test_cycle_error_names_the_cycle(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        parent_path = tmp_path / "parent.json"

        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./parent.json"],
                "conventions": [],
            },
        )
        write_json(
            parent_path,
            {
                "version": "v1",
                "extends": ["./konpy.json"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == (
            "Config inheritance cycle detected: "
            f"{config_path.resolve()} -> {parent_path.resolve()} -> {config_path.resolve()}."
        )

    def test_missing_parent_path_returns_clear_config_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./missing.json"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "./missing.json" from {config_path.resolve()}: could not read '
            f"file at {(tmp_path / 'missing.json').resolve()}."
        )

    def test_parent_relative_extends_resolve_relative_to_parent_config_dir(
        self,
        tmp_path: Path,
    ) -> None:
        configs_dir = tmp_path / "configs"
        base_dir = configs_dir / "base"
        base_dir.mkdir(parents=True)
        configs_dir.mkdir(exist_ok=True)

        write_json(
            base_dir / "base.json",
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
        write_json(
            configs_dir / "team.json",
            {
                "version": "v1",
                "extends": ["./base/base.json"],
                "conventions": [
                    {
                        "name": "team-rule",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["pyproject.toml"]},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./configs/team.json"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == [
            "base-rule",
            "team-rule",
        ]

    def test_parent_relative_convention_sources_work_for_child_references(
        self,
        tmp_path: Path,
    ) -> None:
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()

        write_json(
            shared_dir / "local-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "package-must-have-readme",
                        "description": "Every package must have README.",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )
        write_json(
            shared_dir / "base.json",
            {
                "version": "v1",
                "conventionSources": {"common": "./local-conventions.json"},
                "conventions": [],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./shared/base.json"],
                "conventions": ["common/package-must-have-readme"],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.conventions[0].name == "package-must-have-readme"
        assert result.value.conventions[0].paths == "packages/{packageName}"

    def test_package_extends_loads_installed_distribution(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-loader-base-config",
            import_package="konpy_test_loader_base_config",
            package_json=raw_config_package("base-rule"),
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["konpy-test-loader-base-config"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert [convention.name for convention in result.value.conventions] == ["base-rule"]

    def test_package_extends_with_package_convention_sources_expands_inherited_refs(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-loader-parent-conventions",
            import_package="konpy_test_loader_parent_conventions",
            package_json=reusable_convention_package("package-must-have-readme"),
        )
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-loader-parent-config",
            import_package="konpy_test_loader_parent_config",
            package_json={
                "version": "v1",
                "conventionSources": {
                    "common": "konpy-test-loader-parent-conventions",
                },
                "conventions": ["common/package-must-have-readme"],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["konpy-test-loader-parent-config"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.conventionSources == {
            "common": "konpy-test-loader-parent-conventions"
        }
        assert result.value.conventions[0].name == "package-must-have-readme"

    def test_bare_package_extends_is_explicitly_unsupported(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["@scope/base-config"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == (
            f'Config extends "@scope/base-config" from {config_path.resolve()}: invalid Python '
            "distribution name. Bare package sources must match "
            "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
        )

    def test_post_merge_placeholder_validation_still_runs_after_inheritance(
        self,
        tmp_path: Path,
    ) -> None:
        parent_path = tmp_path / "base.json"
        config_path = tmp_path / CONFIG_FILENAME

        write_json(
            parent_path,
            {
                "version": "v1",
                "conventions": [
                    {
                        "name": "broken-inherited",
                        "paths": "packages/{packageName}",
                        "must": {"haveFiles": ["${missing}.py"]},
                    }
                ],
            },
        )
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'Convention "broken-inherited" references "${missing}"' in result.error


def plugin_source(*, key: str = "requireMarker", value_model: str = "str") -> str:
    return f'''
from konpy.plugin import PredicatePlugin


def handler(*, expected, context, structure, convention_name=None, severity=None):
    return []


plugin = PredicatePlugin(
    key="{key}",
    value_model={value_model},
    handler=handler,
    forbidden_message_template='Forbidden marker "{{resolved_value}}"',
)
'''


def install_marker_plugin(
    *,
    tmp_path: Path,
    monkeypatch,
    distribution_name: str = "konpy-test-loader-plugin",
    import_package: str = "konpy_test_loader_plugin",
    key: str = "requireMarker",
    value_model: str = "str",
) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name=distribution_name,
        import_package=import_package,
        modules={"rules": plugin_source(key=key, value_model=value_model)},
        entry_points={
            "konpy.predicates": {
                key: f"{import_package}.rules:plugin",
            }
        },
    )


class TestLoadConfigPlugins:
    def test_loads_plugin_predicate_when_plugin_is_listed(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-plugin"],
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )

        result = load_config_runtime(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.config.plugins == ["konpy-test-loader-plugin"]
        assert "requireMarker" in result.value.predicate_registry.handlers
        assert result.value.config.conventions[0].must is not None
        assert result.value.config.conventions[0].must.model_extra == {
            "requireMarker": "PLUGIN_OK"
        }

    def test_installed_plugin_is_not_auto_discovered_when_not_listed(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        config_path = tmp_path / CONFIG_FILENAME
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

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'unknown predicate key "requireMarker"' in result.error

    def test_missing_plugin_distribution_fails_before_scan(self, tmp_path: Path) -> None:
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-missing-plugin"],
                "conventions": [],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert result.error == (
            'Plugin "konpy-test-loader-missing-plugin": installed Python distribution '
            "not found. Install it or remove it from plugins."
        )

    def test_invalid_plugin_value_fails_config_validation(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            value_model="list[str]",
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-plugin"],
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'plugin predicate "requireMarker" value is invalid' in result.error

    def test_plugin_predicate_in_reusable_convention_source_validates(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        write_json(
            tmp_path / "plugin-conventions.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "plugin-reusable-rule",
                        "description": "Reusable plugin rule.",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-plugin"],
                "conventionSources": {"plugin": "./plugin-conventions.json"},
                "conventions": ["plugin/plugin-reusable-rule"],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.conventions[0].must is not None
        assert result.value.conventions[0].must.model_extra == {
            "requireMarker": "PLUGIN_OK"
        }

    def test_plugin_predicate_placeholders_are_validated(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-plugin"],
                "conventions": [
                    {
                        "name": "plugin-rule",
                        "paths": "src/{name}.py",
                        "must": {"requireMarker": "${missing}"},
                    }
                ],
            },
        )

        result = load_config(config_path=config_path)

        assert isinstance(result, Err)
        assert 'Convention "plugin-rule" references "${missing}" in must.requireMarker' in (
            result.error
        )

    def test_parent_declared_plugin_validates_parent_plugin_predicate(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
        parent_path = tmp_path / "base.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-loader-plugin"],
                "conventions": [
                    {
                        "name": "parent-plugin-rule",
                        "paths": "src/*.py",
                        "must": {"requireMarker": "PLUGIN_OK"},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "conventions": [],
            },
        )

        result = load_config_runtime(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.config.plugins == ["konpy-test-loader-plugin"]
        assert result.value.config.conventions[0].name == "parent-plugin-rule"
        assert result.value.config.conventions[0].must is not None
        assert result.value.config.conventions[0].must.model_extra == {
            "requireMarker": "PLUGIN_OK"
        }

    def test_child_plugin_is_appended_after_parent_plugins(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_marker_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-parent-plugin",
            import_package="konpy_test_parent_plugin",
            key="parentRule",
        )
        install_marker_plugin(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-child-plugin",
            import_package="konpy_test_child_plugin",
            key="childRule",
        )
        parent_path = tmp_path / "base.json"
        write_json(
            parent_path,
            {
                "version": "v1",
                "plugins": ["konpy-test-parent-plugin"],
                "conventions": [
                    {
                        "name": "parent-plugin-rule",
                        "paths": "src/*.py",
                        "must": {"parentRule": "PARENT"},
                    }
                ],
            },
        )
        config_path = tmp_path / CONFIG_FILENAME
        write_json(
            config_path,
            {
                "version": "v1",
                "extends": ["./base.json"],
                "plugins": ["konpy-test-child-plugin"],
                "conventions": [
                    {
                        "name": "child-plugin-rule",
                        "paths": "src/*.py",
                        "must": {"childRule": "CHILD"},
                    }
                ],
            },
        )

        result = load_config_runtime(config_path=config_path)

        assert isinstance(result, Ok)
        assert result.value.config.plugins == [
            "konpy-test-parent-plugin",
            "konpy-test-child-plugin",
        ]
        assert "parentRule" in result.value.predicate_registry.handlers
        assert "childRule" in result.value.predicate_registry.handlers
