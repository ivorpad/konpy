"""Tests for warning-free parsing of analyzed source."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import app
from konpy.python_ast.quiet_parse import quiet_parse

runner = CliRunner()

# An invalid escape sequence: CPython emits SyntaxWarning at parse time.
_INVALID_ESCAPE = 'PATTERN = "^[A-Za-z]{4}\\d{4}$"\n'


class TestQuietParse:
    def test_invalid_escape_emits_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            quiet_parse(_INVALID_ESCAPE, filename="vendored.py")

        assert caught == []

    def test_syntax_errors_still_raise(self) -> None:
        with pytest.raises(SyntaxError):
            quiet_parse("def broken(:\n", filename="broken.py")

    def test_type_comments_are_supported(self) -> None:
        module = quiet_parse(
            "x = []  # type: list[int]\n", filename="typed.py", type_comments=True
        )

        assert module.body


class TestReportEmitsNoParseWarnings:
    def test_analyzed_source_warnings_stay_out_of_the_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        vendored = tmp_path / "vendor"
        vendored.mkdir()
        (vendored / "base_test.py").write_text(_INVALID_ESCAPE, encoding="utf-8")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "SyntaxWarning" not in result.output
        assert not [item for item in caught if item.category is SyntaxWarning]
