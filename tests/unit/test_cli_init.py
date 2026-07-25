"""Tests for `konpy init` (starter-config generation)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import app
from konpy.cli.init import INIT_TEMPLATE
from konpy.config.errors import Ok
from konpy.config.loader import load_config

runner = CliRunner()


class TestInitCommand:
    def test_writes_starter_config_and_prints_next_steps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == INIT_TEMPLATE
        assert "Wrote konpy.json" in result.output
        assert "konpy check" in result.output
        assert "konpy docs" in result.output

    def test_refuses_to_overwrite_an_existing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        existing = '{"version": "v1", "conventions": []}\n'
        (tmp_path / "konpy.json").write_text(existing, encoding="utf-8")

        result = runner.invoke(app, ["init"])

        assert result.exit_code == 1
        assert (tmp_path / "konpy.json").read_text(encoding="utf-8") == existing
        assert "already exists" in result.output

    def test_starter_config_passes_the_real_config_loader(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = load_config(config_path=tmp_path / "konpy.json")

        assert isinstance(result, Ok)
        assert result.value.version == "v1"
        assert result.value.unusedCode is not None

        names = [convention.name for convention in result.value.conventions]
        assert len(names) == 18
        for expected in (
            "project-root-uses-src-layout",
            "init-files-are-barrels",
            "max-module-length",
            "no-typing-any",
            "annotated-public-functions",
            "docstrings-on-public-api",
            "tests-mirror-package-modules",
            "no-duplicate-functions",
        ):
            assert expected in names

    def test_starter_ratchets_are_warnings_the_rest_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = load_config(config_path=tmp_path / "konpy.json")

        assert isinstance(result, Ok)
        warning_names = {
            convention.name
            for convention in result.value.conventions
            if convention.severity == "warning"
        }
        assert warning_names == {
            "no-todo-comments",
            "no-repeated-string-literals",
            "no-duplicate-functions",
        }
