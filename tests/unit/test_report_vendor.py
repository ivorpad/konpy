"""Tests for vendor/template/gitignored detection (`konpy.core._report_vendor`)
and its integration into the zero-config report.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import konpy.core._report_vendor as report_vendor
from konpy.cli.app import _preprocess_argv, app
from konpy.core._report_vendor import detect_vendor_paths

runner = CliRunner()


@pytest.fixture(autouse=True)
def _skip_external_tool_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the real ruff/basedpyright/import-linter subprocesses.

    These tests exercise vendor/template detection and its wiring into the
    report, not external-tool integration -- that's covered directly, with
    fake runners, in test_report_tools.py.
    """
    monkeypatch.setattr("konpy.core.report.collect_tool_lanes", lambda root, **_: ())


_DUPLICATE_FUNCTION = (
    "def {name}(values: list[int]) -> int:\n"
    '    """Sum positives."""\n'
    "    total = 0\n"
    "    for value in values:\n"
    "        if value > 0:\n"
    "            total += value\n"
    "    return total\n"
)


class TestTemplateDetection:
    def test_double_brace_segment_is_template(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["proj/{{cookiecutter.name}}/app.py"])

        assert result.template_files == {"proj/{{cookiecutter.name}}/app.py"}
        assert result.matched_roots == ("proj/{{cookiecutter.name}}/",)

    def test_open_brace_without_close_is_not_template(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["proj/{{not_closed/app.py"])

        assert result.template_files == frozenset()

    def test_close_brace_without_open_is_not_template(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["proj/not_opened}}/app.py"])

        assert result.template_files == frozenset()

    def test_directory_holding_cookiecutter_json_marks_the_whole_tree(
        self, tmp_path: Path
    ) -> None:
        template = tmp_path / "template"
        template.mkdir()
        (template / "cookiecutter.json").write_text("{}\n", encoding="utf-8")
        files = ["template/hooks/post_gen.py", "other/app.py"]

        result = detect_vendor_paths(tmp_path, files)

        assert result.template_files == {"template/hooks/post_gen.py"}
        assert "template/" in result.matched_roots

    def test_no_cookiecutter_json_and_no_braces_is_not_template(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["template/hooks/post_gen.py"])

        assert result.template_files == frozenset()

    def test_cookiecutter_json_in_an_unrelated_sibling_does_not_mark_this_tree(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "other").mkdir()
        (tmp_path / "other" / "cookiecutter.json").write_text("{}\n", encoding="utf-8")

        result = detect_vendor_paths(tmp_path, ["template/app.py"])

        assert result.template_files == frozenset()


class TestVendoredDetection:
    @pytest.mark.parametrize(
        "name",
        ["downloads", "vendor", "vendors", "third_party", "thirdparty", "_vendor"],
    )
    def test_reserved_dir_names_are_vendored(self, tmp_path: Path, name: str) -> None:
        result = detect_vendor_paths(tmp_path, [f"{name}/pkg/mod.py"])

        assert result.vendored_files == {f"{name}/pkg/mod.py"}
        assert result.matched_roots == (f"{name}/",)

    def test_dir_name_with_extra_suffix_is_not_vendored(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["vendor_utils/mod.py"])

        assert result.vendored_files == frozenset()

    def test_snapshot_dir_with_hex_revision_is_vendored(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["libs-x@a1b2c3d4/mod.py"])

        assert result.vendored_files == {"libs-x@a1b2c3d4/mod.py"}

    def test_branch_name_after_at_is_not_a_snapshot(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["pkg@main/mod.py"])

        assert result.vendored_files == frozenset()

    def test_short_hex_revision_is_not_a_snapshot(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["pkg@abc123/mod.py"])  # 6 chars, below the floor

        assert result.vendored_files == frozenset()

    def test_bare_at_sign_with_no_name_is_not_a_snapshot(self, tmp_path: Path) -> None:
        result = detect_vendor_paths(tmp_path, ["@1234567/mod.py"])

        assert result.vendored_files == frozenset()


class TestPrecedence:
    def test_template_wins_over_vendored_for_the_same_file(self, tmp_path: Path) -> None:
        path = "vendor/{{cookiecutter.name}}/app.py"

        result = detect_vendor_paths(tmp_path, [path])

        assert path in result.template_files
        assert path not in result.vendored_files


class TestGitignoredDetection:
    def test_gitignored_untracked_file_is_detected(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
        build = tmp_path / "build"
        build.mkdir()
        (build / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = detect_vendor_paths(tmp_path, ["build/mod.py", "src/mod.py"])

        assert result.gitignored_files == {"build/mod.py"}

    def test_tracked_file_is_not_gitignored(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)

        result = detect_vendor_paths(tmp_path, ["src/mod.py"])

        assert result.gitignored_files == frozenset()

    def test_untracked_but_not_ignored_file_is_not_reported(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "scratch.py").write_text("x = 1\n", encoding="utf-8")

        result = detect_vendor_paths(tmp_path, ["scratch.py"])

        assert result.gitignored_files == frozenset()

    def test_not_a_git_repo_returns_empty_set(self, tmp_path: Path) -> None:
        (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = detect_vendor_paths(tmp_path, ["mod.py"])

        assert result.gitignored_files == frozenset()

    def test_missing_git_binary_returns_empty_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("git")

        monkeypatch.setattr(report_vendor.subprocess, "run", _raise)

        result = detect_vendor_paths(tmp_path, ["mod.py"])

        assert result.gitignored_files == frozenset()

    def test_file_already_classified_as_vendored_counts_once(self, tmp_path: Path) -> None:
        # A vendored dir that also happens to be gitignored must not be
        # double-counted across the two sets -- the header count is the
        # union, so precedence keeps each file in exactly one bucket.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / ".gitignore").write_text("vendor/\n", encoding="utf-8")
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = detect_vendor_paths(tmp_path, ["vendor/mod.py"])

        assert result.vendored_files == {"vendor/mod.py"}
        assert result.gitignored_files == frozenset()


class TestReportIntegration:
    def test_default_drops_cookiecutter_scaffold_from_every_lane(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        template = tmp_path / "scaffold" / "{{cookiecutter.project_slug}}"
        template.mkdir(parents=True)
        (template / "app_a.py").write_text(
            _DUPLICATE_FUNCTION.format(name="tpl_a"), encoding="utf-8"
        )
        (template / "app_b.py").write_text(
            _DUPLICATE_FUNCTION.format(name="tpl_b"), encoding="utf-8"
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def kept() -> int:\n    return 1\n", encoding="utf-8")

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "1 files" in result.output
        assert "(2 vendored/template/ignored)" in result.output
        # Dropped before parsing, so the group is never even computed.
        assert "tpl_a" not in result.output
        assert "no repeated literals or duplicate functions" in result.output

    def test_include_vendored_labels_cookiecutter_duplicate_group(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        template = tmp_path / "scaffold" / "{{cookiecutter.project_slug}}"
        template.mkdir(parents=True)
        (template / "app_a.py").write_text(
            _DUPLICATE_FUNCTION.format(name="tpl_a"), encoding="utf-8"
        )
        (template / "app_b.py").write_text(
            _DUPLICATE_FUNCTION.format(name="tpl_b"), encoding="utf-8"
        )

        result = runner.invoke(app, ["report", "--include-vendored"])

        assert result.exit_code == 0
        assert "2 files" in result.output
        assert "tpl_a" in result.output
        assert "[generator template]" in result.output

    def test_include_vendored_labels_vendored_duplicate_group(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        vendor = tmp_path / "third_party"
        vendor.mkdir()
        (vendor / "a.py").write_text(_DUPLICATE_FUNCTION.format(name="vend_a"), encoding="utf-8")
        (vendor / "b.py").write_text(_DUPLICATE_FUNCTION.format(name="vend_b"), encoding="utf-8")

        result = runner.invoke(app, ["report", "--include-vendored"])

        assert result.exit_code == 0
        assert "[vendored]" in result.output

    def test_vendored_tree_drops_counts_but_keeps_references_alive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "helpers.py").write_text(
            "def hand_written() -> int:\n    return 1\n", encoding="utf-8"
        )
        vendor = tmp_path / "third_party" / "pkg"
        vendor.mkdir(parents=True)
        (vendor / "mod.py").write_text(
            "from src.helpers import hand_written\n\n"
            "def vendored_dead() -> int:\n    return 2\n\n"
            "hand_written()\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "1 files" in result.output
        assert "(1 vendored/template/ignored)" in result.output
        # A dead def inside the vendored tree never surfaces at all -- it is
        # not even parsed into the report's own structures.
        assert "vendored_dead" not in result.output
        # The hand-written def is referenced only from vendored code and must
        # stay used, not reported dead (reference-only, like generated code).
        assert 'Unused definition "hand_written"' not in result.output

    def test_vendored_files_are_excluded_from_coverage(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text(
            '"""Documented module."""\n\n\n'
            'def documented() -> int:\n    """Docstring."""\n    return 1\n',
            encoding="utf-8",
        )
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "mod.py").write_text(
            "def undocumented() -> int:\n    return 2\n", encoding="utf-8"
        )

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "modules 1/1 (100%)" in result.output
        assert "public functions 1/1 (100%)" in result.output
        assert "non-vendor" in result.output

    def test_vendored_literals_do_not_count_toward_repetition(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        shared = 'SHARED = "a distinctly repeatable literal value"\n'
        (src / "a.py").write_text(shared, encoding="utf-8")
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "b.py").write_text(shared, encoding="utf-8")
        (vendor / "c.py").write_text(shared, encoding="utf-8")

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "a distinctly repeatable literal value" not in result.output

    def test_header_and_note_list_matched_roots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def kept() -> int:\n    return 1\n", encoding="utf-8")
        for name in ("downloads", "vendor"):
            directory = tmp_path / name
            directory.mkdir()
            (directory / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "(2 vendored/template/ignored)" in result.output
        assert "note: skipped vendor/template trees:" in result.output
        assert "downloads/" in result.output
        assert "vendor/" in result.output

    def test_note_caps_matched_roots_at_three_with_ellipsis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def kept() -> int:\n    return 1\n", encoding="utf-8")
        for name in ("downloads", "third_party", "vendor", "vendors"):
            directory = tmp_path / name
            directory.mkdir()
            (directory / "mod.py").write_text("x = 1\n", encoding="utf-8")

        result = runner.invoke(app, ["report"])

        note_line = next(
            line for line in result.output.splitlines() if "skipped vendor/template trees" in line
        )

        # Sorted alphabetically, only the first three roots are shown.
        assert "downloads/" in note_line
        assert "third_party/" in note_line
        assert "vendor/" in note_line
        assert "vendors/" not in note_line
        assert note_line.rstrip().endswith("...")

    def test_no_vendor_matches_renders_no_count_and_no_note(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def kept() -> int:\n    return 1\n", encoding="utf-8")

        result = runner.invoke(app, ["report"])

        assert result.exit_code == 0
        assert "vendored/template/ignored" not in result.output
        assert "skipped vendor/template trees" not in result.output

    def test_include_vendored_flag_restores_full_counting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def kept() -> int:\n    return 1\n", encoding="utf-8")
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "mod.py").write_text(
            "def vendored_dead() -> int:\n    return 2\n", encoding="utf-8"
        )

        default = runner.invoke(app, ["report"])
        included = runner.invoke(app, ["report", "--include-vendored"])

        assert default.exit_code == 0
        assert included.exit_code == 0
        assert "1 files" in default.output
        assert "2 files" in included.output
        assert "vendored/template/ignored" not in included.output
        assert "vendored_dead" not in default.output
        assert 'Unused definition "vendored_dead"' in included.output


class TestArgvRouting:
    def test_bare_include_vendored_routes_to_report(self) -> None:
        assert _preprocess_argv(["--include-vendored"]) == ["report", "--include-vendored"]

    def test_explicit_report_subcommand_is_unaffected(self) -> None:
        assert _preprocess_argv(["report", "--include-vendored"]) == [
            "report",
            "--include-vendored",
        ]
