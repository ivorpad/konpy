"""Tests for `konpy docs` and the bundled reference-doc loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli import _packaged_docs
from konpy.cli.app import app
from konpy.config.errors import Err, Ok

runner = CliRunner()


class TestDocsCommand:
    def test_no_topic_lists_available_topics(self) -> None:
        result = runner.invoke(app, ["docs"])

        assert result.exit_code == 0
        assert "predicates" in result.output
        assert "configuration" in result.output
        assert "konpy docs <topic>" in result.output

    def test_prints_the_named_reference_doc(self) -> None:
        result = runner.invoke(app, ["docs", "predicates"])

        assert result.exit_code == 0
        assert result.output.startswith("# Predicates")

    def test_unknown_topic_exits_one_and_lists_topics(self) -> None:
        result = runner.invoke(app, ["docs", "no-such-topic"])

        assert result.exit_code == 1
        assert "Unknown docs topic: no-such-topic" in result.output
        assert "predicates" in result.output


class TestPackagedDocs:
    def test_reads_from_the_source_tree_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "sample.md").write_text("# Sample\n\nbody\n", encoding="utf-8")
        monkeypatch.setattr(_packaged_docs, "_source_tree_reference_dir", lambda: tmp_path)

        result = _packaged_docs.read_reference_doc("sample")

        assert isinstance(result, Ok)
        assert result.value.startswith("# Sample")

    def test_lists_topics_from_the_source_tree_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "beta.md").write_text("# B\n", encoding="utf-8")
        (tmp_path / "alpha.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
        monkeypatch.setattr(_packaged_docs, "_source_tree_reference_dir", lambda: tmp_path)

        assert _packaged_docs.available_reference_topics() == ["alpha", "beta"]

    def test_missing_doc_everywhere_is_an_err(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_packaged_docs, "_source_tree_reference_dir", lambda: tmp_path)

        result = _packaged_docs.read_reference_doc("absent")

        assert isinstance(result, Err)
        assert "docs/reference/absent.md" in result.error
