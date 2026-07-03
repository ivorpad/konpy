from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fake_distribution import install_fake_distribution


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_file(path: Path, value: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _plugin_source() -> str:
    return '''
from konpy.plugin import PredicatePlugin, create_diagnostic


def handler(*, expected, context, structure, convention_name=None, severity=None):
    source = context.file_system.read_file(context.path)
    if expected in source:
        return []
    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="requireMarker",
            message=f'Missing marker "{expected}"',
            convention_name=convention_name,
            severity=severity,
        )
    ]


plugin = PredicatePlugin(
    key="requireMarker",
    value_model=str,
    handler=handler,
    forbidden_message_template='Forbidden marker "{resolved_value}"',
)
'''


def _install_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_distribution(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        distribution_name="konpy-e2e-plugin",
        import_package="konpy_e2e_plugin",
        modules={"rules": _plugin_source()},
        entry_points={
            "konpy.predicates": {
                "requireMarker": "konpy_e2e_plugin.rules:plugin",
            }
        },
    )


def _make_project(*, tmp_path: Path, marker_present: bool) -> Path:
    project_dir = tmp_path / ("plugin-project-clean" if marker_present else "plugin-project-broken")
    _write_file(
        project_dir / "src" / "module.py",
        "# PLUGIN_OK\nVALUE = 1\n" if marker_present else "VALUE = 1\n",
    )
    _write_json(
        project_dir / "konpy.json",
        {
            "version": "v1",
            "plugins": ["konpy-e2e-plugin"],
            "conventions": [
                {
                    "name": "module-marker",
                    "paths": "src/*.py",
                    "must": {"requireMarker": "PLUGIN_OK"},
                }
            ],
        },
    )
    return project_dir


def test_plugin_predicate_project_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    _install_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
    project_dir = _make_project(tmp_path=tmp_path, marker_present=True)

    exit_code, stdout, stderr = run_cli(project_dir, "validate")

    assert exit_code == 0
    assert stderr == ""
    assert "Configuration is valid." in stdout


def test_plugin_predicate_project_checks_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    _install_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
    project_dir = _make_project(tmp_path=tmp_path, marker_present=True)

    exit_code, stdout, stderr = run_cli(project_dir, "check")

    assert exit_code == 0
    assert stderr == ""
    assert "No violations found." in stdout


def test_plugin_predicate_project_reports_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    _install_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
    project_dir = _make_project(tmp_path=tmp_path, marker_present=False)

    exit_code, stdout, stderr = run_cli(project_dir, "check", "--no-colors")

    assert exit_code == 1
    assert stderr == ""
    assert "src/module.py" in stdout
    assert 'Missing marker "PLUGIN_OK"' in stdout
    assert "module-marker" in stdout


def test_plugin_predicate_requires_explicit_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run_cli,
) -> None:
    _install_plugin(tmp_path=tmp_path, monkeypatch=monkeypatch)
    project_dir = tmp_path / "plugin-project-no-opt-in"
    _write_file(project_dir / "src" / "module.py", "# PLUGIN_OK\n")
    _write_json(
        project_dir / "konpy.json",
        {
            "version": "v1",
            "conventions": [
                {
                    "name": "module-marker",
                    "paths": "src/*.py",
                    "must": {"requireMarker": "PLUGIN_OK"},
                }
            ],
        },
    )

    exit_code, stdout, stderr = run_cli(project_dir, "validate")
    output = f"{stdout}\n{stderr}"

    assert exit_code == 1
    assert 'unknown predicate key "requireMarker"' in output
