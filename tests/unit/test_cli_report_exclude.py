"""Tests for `konpy report --exclude` (caller-supplied report scoping)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from konpy.cli.app import _preprocess_argv, app
from konpy.cli.report import split_exclude_values

runner = CliRunner()


class TestSplitExcludeValues:
    def test_splits_on_commas_and_whitespace(self) -> None:
        assert split_exclude_values(["a/**,b/**"]) == ["a/**", "b/**"]
        assert split_exclude_values(["a/** b/**"]) == ["a/**", "b/**"]
        assert split_exclude_values(["a/**", "b/**"]) == ["a/**", "b/**"]

    def test_preserves_commas_inside_brace_alternation(self) -> None:
        assert split_exclude_values(["**/{tests,docs}/**"]) == ["**/{tests,docs}/**"]
        assert split_exclude_values(["a/**,{b,c}/**"]) == ["a/**", "{b,c}/**"]

    def test_preserves_nested_braces(self) -> None:
        assert split_exclude_values(["{a,{b,c}}/**"]) == ["{a,{b,c}}/**"]

    def test_drops_empty_segments_and_collapses_duplicates(self) -> None:
        assert split_exclude_values(["a/**,,b/**", "a/**"]) == ["a/**", "b/**"]

    def test_unbalanced_closing_brace_does_not_underflow(self) -> None:
        # A stray `}` must not drive depth negative, which would stop the
        # following comma from splitting. Glob metacharacters keep prefix
        # expansion out of the assertion.
        assert split_exclude_values(["}a/**,b/**"]) == ["}a/**", "b/**"]


class TestBareDirectoryPrefixes:
    def test_metacharacter_free_pattern_also_matches_beneath(self) -> None:
        assert split_exclude_values(["vendor"]) == ["vendor", "vendor/**"]

    def test_trailing_slash_does_not_double_up(self) -> None:
        assert split_exclude_values(["vendor/"]) == ["vendor/", "vendor/**"]

    def test_glob_patterns_are_left_alone(self) -> None:
        assert split_exclude_values(["vendor/**"]) == ["vendor/**"]
        assert split_exclude_values(["**/{a,b}/**"]) == ["**/{a,b}/**"]

    def test_bare_directory_excludes_its_contents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "mod.py").write_text(
            "def kept() -> int:\n    return 1\n", encoding="utf-8"
        )
        vendored = tmp_path / "vendor" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "mod.py").write_text(
            "def dropped() -> int:\n    return 2\n", encoding="utf-8"
        )

        result = runner.invoke(app, ["report", "--exclude", "vendor"])

        assert result.exit_code == 0
        assert "1 file" in result.output
        assert "dropped" not in result.output
        assert "kept" in result.output


class TestUnmatchedExcludeWarning:
    def test_pattern_matching_nothing_warns_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = runner.invoke(
            app, ["report", "--exclude", "vendr"], catch_exceptions=False
        )

        # One typo yields one warning, not one per prefix-expanded companion.
        assert result.output.count("matched nothing: vendr") == 1
        assert "matched nothing: vendr/**" not in result.output

    def test_matching_pattern_does_not_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        vendored = tmp_path / "vendor"
        vendored.mkdir()
        (vendored / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = runner.invoke(app, ["report", "--exclude", "vendor"])

        assert "matched nothing" not in result.output


class TestPreprocessArgvExpandsExclude:
    def test_exclude_without_a_subcommand_routes_to_report(self) -> None:
        assert _preprocess_argv(["--exclude", "vendor"]) == [
            "report",
            "--exclude",
            "vendor",
        ]

    def test_equals_form_without_a_subcommand_routes_to_report(self) -> None:
        assert _preprocess_argv(["--exclude=vendor"]) == ["report", "--exclude=vendor"]

    def test_other_flags_still_imply_check(self) -> None:
        assert _preprocess_argv(["--files", "a.py"]) == ["check", "--files", "a.py"]

    def test_explicit_subcommand_is_never_overridden(self) -> None:
        assert _preprocess_argv(["report", "--exclude", "vendor"]) == [
            "report",
            "--exclude",
            "vendor",
        ]

    def test_expands_space_separated_before_next_flag(self) -> None:
        assert _preprocess_argv(["report", "--exclude", "a/**", "b/**"]) == [
            "report",
            "--exclude",
            "a/**",
            "--exclude",
            "b/**",
        ]

    def test_equals_form_untouched(self) -> None:
        assert _preprocess_argv(["report", "--exclude=a/**"]) == [
            "report",
            "--exclude=a/**",
        ]


class TestReportExcludeOption:
    def _tree(self, root: Path) -> None:
        """A source module plus a vendored copy that references it."""
        src = root / "src"
        src.mkdir()
        (src / "mod.py").write_text(
            "def dead_helper() -> int:\n    return 1\n", encoding="utf-8"
        )
        vendored = root / "vendor" / "pkg"
        vendored.mkdir(parents=True)
        (vendored / "mod.py").write_text(
            "def vendored_orphan() -> int:\n    return 2\n", encoding="utf-8"
        )

    def test_excluded_tree_leaves_every_lane_and_the_header(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._tree(tmp_path)

        unscoped = runner.invoke(app, ["report"])
        scoped = runner.invoke(app, ["report", "--exclude", "vendor/**"])

        assert unscoped.exit_code == 0
        assert scoped.exit_code == 0
        assert "2 files" in unscoped.output
        assert "1 file" in scoped.output
        assert "vendored_orphan" in unscoped.output
        assert "vendored_orphan" not in scoped.output
        # The kept file is still analyzed rather than dropped with the exclude.
        assert "dead_helper" in scoped.output

    def test_comma_space_and_repeated_forms_agree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        self._tree(tmp_path)
        other = tmp_path / "generated"
        other.mkdir()
        (other / "mod.py").write_text(
            "def generated_orphan() -> int:\n    return 3\n", encoding="utf-8"
        )

        comma = runner.invoke(app, ["report", "--exclude", "vendor/**,generated/**"])
        spaced = runner.invoke(app, ["report", "--exclude", "vendor/** generated/**"])
        repeated = runner.invoke(
            app, ["report", "--exclude", "vendor/**", "--exclude", "generated/**"]
        )
        # `_preprocess_argv` (invoked by `main()` in real usage) is what turns
        # one unquoted `--exclude a b` occurrence into repeated flags.
        expanded = runner.invoke(
            app, _preprocess_argv(["report", "--exclude", "vendor/**", "generated/**"])
        )

        for result in (comma, spaced, repeated, expanded):
            assert result.exit_code == 0
            assert "1 file" in result.output
            assert "vendored_orphan" not in result.output
            assert "generated_orphan" not in result.output

    def test_excluded_references_cannot_mask_dead_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text(
            "def dead_helper() -> int:\n    return 1\n", encoding="utf-8"
        )
        vendored = tmp_path / "vendor"
        vendored.mkdir()
        (vendored / "caller.py").write_text(
            "from src.mod import dead_helper\n\nvalue = dead_helper()\n",
            encoding="utf-8",
        )

        masked = runner.invoke(app, ["report"])
        scoped = runner.invoke(app, ["report", "--exclude", "vendor/**"])

        assert 'Unused definition "dead_helper"' not in masked.output
        assert 'Unused definition "dead_helper"' in scoped.output

    def test_conventions_lane_is_not_scoped_by_exclude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        vendored = tmp_path / "vendor"
        vendored.mkdir()
        (vendored / "mod.py").write_text("# FIXME: left behind\n", encoding="utf-8")
        (tmp_path / "konpy.json").write_text(
            '{"version": "v1", "conventions": [{"name": "no-fixme", '
            '"paths": "vendor/**/*.py", "mustNot": {"matchContent": '
            '["FIXME"]}}]}\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["report", "--exclude", "vendor/**"])

        assert result.exit_code == 1
        assert "no-fixme" in result.output
