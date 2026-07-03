from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fake_distribution import install_fake_distribution


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_file(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _make_package_extends_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name="konpy-e2e-extends-common-conventions",
        import_package="konpy_e2e_extends_common_conventions",
        package_json={
            "conventionSpecVersion": "v1",
            "conventions": [
                {
                    "name": "package-must-have-py-typed",
                    "description": "Packages must include a py.typed marker.",
                    "must": {
                        "haveFiles": ["py.typed"],
                    },
                }
            ],
        },
    )
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name="konpy-e2e-base-config",
        import_package="konpy_e2e_base_config",
        package_json={
            "version": "v1",
            "conventionSources": {
                "common": "konpy-e2e-extends-common-conventions",
            },
            "conventions": [
                {
                    "use": "common/package-must-have-py-typed",
                    "paths": "packages/{packageName}",
                }
            ],
        },
    )

    project_dir = tmp_path / "project"
    _write_file(project_dir / "packages" / "sample" / "py.typed")
    _write_json(
        project_dir / "konpy.json",
        {
            "version": "v1",
            "extends": ["konpy-e2e-base-config"],
            "conventions": [],
        },
    )
    return project_dir


def test_config_extends_variant_validates_clean(fixtures_dir: Path, run_cli) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "config-extends-variants"),
        "validate",
    )

    assert exit_code == 0
    assert stderr == ""
    assert "Configuration is valid." in stdout


def test_config_extends_variant_checks_clean(fixtures_dir: Path, run_cli) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "config-extends-variants"),
        "check",
    )

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


def test_config_extends_package_validates_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    fixture = _make_package_extends_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)

    exit_code, stdout, stderr = run_cli(fixture, "validate")

    assert exit_code == 0
    assert stderr == ""
    assert "Configuration is valid." in stdout


def test_config_extends_package_checks_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    fixture = _make_package_extends_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)

    exit_code, stdout, stderr = run_cli(fixture, "check")

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


def test_config_extends_variant_broken_surfaces_replacement_and_reusable_violations(
    fixtures_dir: Path,
    run_cli,
) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "config-extends-variants-broken"),
        "check",
    )

    assert exit_code == 1
    assert stderr == ""
    assert "Missing required file: pyproject.toml" in stdout
    assert "Missing required file: py.typed" in stdout
    assert "Missing required file: LICENSE" not in stdout
