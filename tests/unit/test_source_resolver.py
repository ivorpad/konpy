import json
from pathlib import Path

import pytest

from konpy.config.errors import Err, Ok
from konpy.config.source_resolver import classify_source, resolve_sources
from tests.fake_distribution import install_fake_distribution, reusable_convention_package


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def invalid_package_name_error(prefix: str, value: str) -> str:
    return (
        f'Convention source "{prefix}" → "{value}": invalid Python distribution name. '
        "Bare package sources must match [A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
    )


def not_installed_error(prefix: str, value: str) -> str:
    return (
        f'Convention source "{prefix}" → "{value}": installed Python distribution not found. '
        "Install it or use a local path in conventionSources."
    )


def missing_json_error(prefix: str, value: str, import_package: str) -> str:
    return (
        f'Convention source "{prefix}" → "{value}": installed Python distribution does not '
        "contain konpy.json. Looked for "
        f"{import_package}/konpy.json and a distribution file named konpy.json."
    )


class TestClassifySource:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", "empty"),
            ("   ", "empty"),
            ("./local.json", "path"),
            ("../local.json", "path"),
            ("/abs/path.json", "path"),
            ("@scope/pkg", "package"),
            ("bare-pkg", "package"),
            ("pkg/subpath", "package"),
        ],
    )
    def test_classifies_sources(self, value: str, expected: str) -> None:
        assert classify_source(value) == expected


class TestResolveSources:
    def test_resolves_path_form_source_relative_to_config_dir(self, tmp_path: Path) -> None:
        write_json(
            tmp_path / "common.json",
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "must-have-readme",
                        "description": "Every package must have a README.md.",
                        "paths": ["packages/{packageName}"],
                        "must": {"haveFiles": ["README.md"]},
                    }
                ],
            },
        )

        result = resolve_sources(
            convention_sources={"common": "./common.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Ok)
        source_map = result.value
        assert source_map["common"]["must-have-readme"].description == (
            "Every package must have a README.md."
        )

    def test_resolves_absolute_path_source(self, tmp_path: Path) -> None:
        abs_path = tmp_path / "abs.json"
        write_json(
            abs_path,
            {
                "conventionSpecVersion": "v1",
                "conventions": [
                    {
                        "name": "x",
                        "description": "y",
                        "paths": "src/*.ts",
                        "must": {"haveType": "file"},
                    }
                ],
            },
        )

        result = resolve_sources(
            convention_sources={"common": str(abs_path)},
            config_dir=tmp_path,
        )

        assert isinstance(result, Ok)
        assert "x" in result.value["common"]

    def test_returns_error_with_failing_path_when_file_is_missing(self, tmp_path: Path) -> None:
        result = resolve_sources(
            convention_sources={"common": "./missing.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == (
            f'Convention source "common" → "./missing.json": could not read file at '
            f"{(tmp_path / 'missing.json').resolve()}."
        )

    def test_returns_error_when_json_is_malformed(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")

        result = resolve_sources(
            convention_sources={"common": "./bad.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == (
            f'Convention source "common" → "./bad.json": malformed JSON at '
            f"{(tmp_path / 'bad.json').resolve()}."
        )

    def test_returns_error_with_clear_path_when_package_schema_is_invalid(
        self,
        tmp_path: Path,
    ) -> None:
        write_json(
            tmp_path / "bad-shape.json",
            {"conventionSpecVersion": "v2", "conventions": []},
        )

        result = resolve_sources(
            convention_sources={"common": "./bad-shape.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert "invalid reusable-convention package" in result.error
        assert "conventionSpecVersion" in result.error

    def test_returns_empty_source_map_for_empty_convention_sources(self, tmp_path: Path) -> None:
        result = resolve_sources(convention_sources={}, config_dir=tmp_path)

        assert result == Ok({})

    def test_rejects_empty_string_source_values_with_precise_error(
        self,
        tmp_path: Path,
    ) -> None:
        result = resolve_sources(convention_sources={"common": ""}, config_dir=tmp_path)

        assert isinstance(result, Err)
        assert result.error == 'Convention source "common" has empty value.'

    def test_rejects_whitespace_only_source_values_with_precise_error(
        self,
        tmp_path: Path,
    ) -> None:
        result = resolve_sources(convention_sources={"common": "   "}, config_dir=tmp_path)

        assert isinstance(result, Err)
        assert result.error == 'Convention source "common" has empty value.'

    def test_resolves_package_source_from_top_level_import_package_konpy_json(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-common-conventions",
            import_package="konpy_test_common_conventions",
            package_json=reusable_convention_package("package-must-have-readme"),
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-common-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Ok)
        assert result.value["common"]["package-must-have-readme"].description == (
            "Every package must have README."
        )

    def test_resolves_package_source_from_dist_info_konpy_json_fallback(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-dist-info-conventions",
            import_package="konpy_test_dist_info_conventions",
            dist_info_json=reusable_convention_package("from-dist-info"),
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-dist-info-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Ok)
        assert "from-dist-info" in result.value["common"]

    def test_package_source_prefers_top_level_import_package_over_dist_info(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-precedence-conventions",
            import_package="konpy_test_precedence_conventions",
            package_json=reusable_convention_package("from-package"),
            dist_info_json=reusable_convention_package("from-dist-info"),
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-precedence-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Ok)
        assert "from-package" in result.value["common"]
        assert "from-dist-info" not in result.value["common"]

    @pytest.mark.parametrize(
        "specifier",
        [
            "@scope/sample-conventions",
            "@scope/conditional-conventions",
            "@konpy-test/definitely-not-installed",
            "@scope/no-konpy-export",
            "@scope/no-exports",
            "@scope/bad-shape",
            "@scope/escape-exports-relative",
            "@scope/malformed-json",
            "pkg/subpath",
        ],
    )
    def test_invalid_python_distribution_names_are_rejected(
        self,
        tmp_path: Path,
        specifier: str,
    ) -> None:
        result = resolve_sources(
            convention_sources={"common": specifier},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == invalid_package_name_error("common", specifier)

    def test_not_installed_bare_package_returns_package_error(self, tmp_path: Path) -> None:
        specifier = "konpy-test-definitely-not-installed-conventions"

        result = resolve_sources(
            convention_sources={"common": specifier},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == not_installed_error("common", specifier)

    def test_installed_distribution_without_konpy_json_returns_clear_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-no-json-conventions",
            import_package="konpy_test_no_json_conventions",
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-no-json-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == missing_json_error(
            "common",
            "konpy-test-no-json-conventions",
            "konpy_test_no_json_conventions",
        )

    def test_installed_distribution_with_malformed_json_returns_clear_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-malformed-conventions",
            import_package="konpy_test_malformed_conventions",
            package_json_text="{ not json",
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-malformed-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == (
            'Convention source "common" → "konpy-test-malformed-conventions": '
            "malformed JSON at package konpy_test_malformed_conventions/konpy.json."
        )

    def test_installed_distribution_with_invalid_reusable_package_returns_clear_error(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        install_fake_distribution(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            distribution_name="konpy-test-invalid-conventions",
            import_package="konpy_test_invalid_conventions",
            package_json={"conventionSpecVersion": "v2", "conventions": []},
        )

        result = resolve_sources(
            convention_sources={"common": "konpy-test-invalid-conventions"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert (
            'Convention source "common" → "konpy-test-invalid-conventions": invalid '
            "reusable-convention package at package "
            "konpy_test_invalid_conventions/konpy.json:"
        ) in result.error
        assert "conventionSpecVersion" in result.error

    def test_auto_detection_routes_local_dot_path_to_path_branch(self, tmp_path: Path) -> None:
        result = resolve_sources(
            convention_sources={"common": "./local.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert "could not read file" in result.error
        assert "./local.json" in result.error

    def test_auto_detection_routes_absolute_path_to_path_branch(self, tmp_path: Path) -> None:
        result = resolve_sources(
            convention_sources={"common": "/abs/path.json"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert "could not read file" in result.error
        assert "/abs/path.json" in result.error

    def test_auto_detection_routes_scoped_npm_package_to_package_branch(
        self,
        tmp_path: Path,
    ) -> None:
        result = resolve_sources(
            convention_sources={"common": "@scope/pkg"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == invalid_package_name_error("common", "@scope/pkg")
        assert "could not read file" not in result.error

    def test_auto_detection_routes_bare_package_to_package_branch(
        self,
        tmp_path: Path,
    ) -> None:
        result = resolve_sources(
            convention_sources={"common": "bare-pkg"},
            config_dir=tmp_path,
        )

        assert isinstance(result, Err)
        assert result.error == not_installed_error("common", "bare-pkg")
        assert "could not read file" not in result.error
