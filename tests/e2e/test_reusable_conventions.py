from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fake_distribution import install_fake_distribution, reusable_convention_package


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _combined(stdout: str, stderr: str) -> str:
    return f"{stdout}\n{stderr}"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_file(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _make_package_source_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name="konpy-e2e-common-conventions",
        import_package="konpy_e2e_common_conventions",
        package_json=reusable_convention_package("package-must-have-readme"),
    )

    project_dir = tmp_path / "project"
    _write_file(project_dir / "packages" / "sample" / "README.md", "# sample\n")
    _write_json(
        project_dir / "konpy.json",
        {
            "version": "v1",
            "conventionSources": {
                "common": "konpy-e2e-common-conventions",
            },
            "conventions": ["common/package-must-have-readme"],
        },
    )
    return project_dir


@pytest.mark.parametrize(
    "name",
    [
        "reusable-convention-string-ref",
        "reusable-convention-object-ref",
        "reusable-convention-must-block-ref",
        "reusable-convention-merge-overrides",
    ],
)
def test_reusable_convention_fixtures_validate(
    fixtures_dir: Path,
    run_cli,
    name: str,
) -> None:
    exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, name), "validate")

    assert exit_code == 0
    assert stderr == ""
    assert "Configuration is valid." in stdout


@pytest.mark.parametrize(
    "name",
    [
        "reusable-convention-string-ref",
        "reusable-convention-object-ref",
        "reusable-convention-must-block-ref",
    ],
)
def test_reusable_convention_fixtures_check_clean(
    fixtures_dir: Path,
    run_cli,
    name: str,
) -> None:
    exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, name), "check")

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


def test_reusable_convention_package_source_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    fixture = _make_package_source_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)

    exit_code, stdout, stderr = run_cli(fixture, "validate")

    assert exit_code == 0
    assert stderr == ""
    assert "Configuration is valid." in stdout


def test_reusable_convention_package_source_checks_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    fixture = _make_package_source_fixture(tmp_path=tmp_path, monkeypatch=monkeypatch)

    exit_code, stdout, stderr = run_cli(fixture, "check")

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


@pytest.mark.parametrize(
    ("name", "missing", "convention"),
    [
        ("reusable-convention-string-ref-broken", "README.md", "package-must-have-readme"),
        ("reusable-convention-object-ref-broken", "index.py", "component-folder-must-have-index"),
        ("reusable-convention-must-block-ref-broken", "index.py", "must-have-index"),
    ],
)
def test_reusable_convention_broken_fixtures_surface_referenced_violations(
    fixtures_dir: Path,
    run_cli,
    name: str,
    missing: str,
    convention: str,
) -> None:
    exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, name), "check")

    assert exit_code == 1
    assert stderr == ""
    assert "Missing required file" in stdout
    assert missing in stdout
    assert convention in stdout


def test_reusable_convention_merge_overrides_warning_exits_zero(
    fixtures_dir: Path,
    run_cli,
) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "reusable-convention-merge-overrides"),
        "check",
    )

    assert exit_code == 0
    assert stderr == ""
    assert "warning" in stdout
    assert "Missing required file: index.py" in stdout
    assert "Found 1 warning." in stdout


def test_reusable_convention_merge_overrides_broken_surfaces_bad_not_skip(
    fixtures_dir: Path,
    run_cli,
) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "reusable-convention-merge-overrides-broken"),
        "check",
    )

    assert exit_code == 1
    assert stderr == ""
    assert "Missing required file: index.py" in stdout
    assert "src/components/Bad" in stdout
    assert "src/components/Skip" not in stdout


def test_reusable_convention_unknown_source_fails_before_scan(
    fixtures_dir: Path,
    run_cli,
) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "reusable-convention-unknown-source"),
        "check",
    )
    output = _combined(stdout, stderr)

    assert exit_code == 1
    assert 'Unknown convention source "missing"' in output
    assert "Checked" not in stdout
    assert "Found" not in stdout


def test_reusable_convention_placeholder_mismatch_fails_check_and_validate(
    fixtures_dir: Path,
    run_cli,
) -> None:
    fixture = _fixture(fixtures_dir, "reusable-convention-placeholder-mismatch")

    for command in ["check", "validate"]:
        exit_code, stdout, stderr = run_cli(fixture, command)
        output = _combined(stdout, stderr)

        assert exit_code == 1
        assert 'Convention "common/component-folder-must-have-named-file"' in output
        assert 'references "${componentName}" in must.haveFiles' in output


def test_reusable_convention_npm_style_source_is_invalid_python_distribution_name(
    fixtures_dir: Path,
    run_cli,
) -> None:
    exit_code, stdout, stderr = run_cli(
        _fixture(fixtures_dir, "reusable-convention-unsupported-npm-source"),
        "check",
    )
    output = _combined(stdout, stderr)

    assert exit_code == 1
    assert (
        'Convention source "common" → "@konpy/common-conventions": invalid Python '
        "distribution name. Bare package sources must match "
        "[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]."
    ) in output
