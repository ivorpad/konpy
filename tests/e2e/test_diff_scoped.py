from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class TestDiffScopedFixture:
    def test_check_exits_zero_for_the_clean_project(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(_fixture(fixtures_dir, "diff-scoped"), "check")

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_files_flag_on_clean_project_still_exits_zero(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        # Selection is convention-level: `--files src/a.py` intersects the
        # convention's matched set ({src/a.py, src/b.py}), so the WHOLE
        # matched set is evaluated -- both files get checked, not just
        # src/a.py.
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped"),
            "check",
            "--files",
            "src/a.py",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Checked 2 file" in stdout


class TestDiffScopedBrokenFixture:
    def test_unscoped_check_reports_the_violation(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "src/b.py" in stdout
        assert "Checked 2 file" in stdout

    def test_files_flag_pointed_at_the_clean_file_still_reports_the_convention_violation(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        # src/a.py itself has no violation, but it shares a convention
        # (matched set {src/a.py, src/b.py}) with src/b.py, which does.
        # `--files src/a.py` selects that convention and evaluates its FULL
        # matched set, so src/b.py's violation is still reported -- never
        # naively limited to the literally-passed file.
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-broken"),
            "check",
            "--files",
            "src/a.py",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "src/b.py" in stdout
        assert "Checked 2 file" in stdout

    def test_files_flag_pointed_at_the_violation_reports_it(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-broken"),
            "check",
            "--files",
            "src/b.py",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "src/b.py" in stdout
        # The convention's full matched set ({src/a.py, src/b.py}) is
        # evaluated once src/b.py puts it in scope, even though only
        # src/b.py was passed to --files.
        assert "Checked 2 file" in stdout

    def test_files_flag_space_list_covers_both_files(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-broken"),
            "check",
            "--files",
            "src/a.py",
            "src/b.py",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "src/b.py" in stdout
        assert "Checked 2 file" in stdout

    def test_files_and_changed_together_is_rejected(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, _stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-broken"),
            "check",
            "--files",
            "src/a.py",
            "--changed",
        )

        assert exit_code == 1
        assert "--files" in stderr
        assert "--changed" in stderr

    def test_changed_flag_selects_the_convention_and_evaluates_its_full_matched_set(
        self,
        fixtures_dir: Path,
        run_cli,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "diff-scoped-broken"
        shutil.copytree(_fixture(fixtures_dir, "diff-scoped-broken"), repo)
        _init_git_repo(repo)
        # Touch src/a.py (already valid, no new violation) after the commit
        # so it is the only file `--changed` puts in scope directly. It
        # shares a convention with src/b.py though, so that convention's
        # FULL matched set -- including the untouched, still-violating
        # src/b.py -- is evaluated and reported.
        (repo / "src" / "a.py").write_text(
            "def process():\n    return 'a-modified'\n",
            encoding="utf-8",
        )

        exit_code, stdout, stderr = run_cli(repo, "check", "--changed")

        assert exit_code == 1
        assert stderr == ""
        assert "src/b.py" in stdout
        assert "Checked 2 file" in stdout


class TestDiffScopedPairedFixture:
    def test_files_flag_pointed_only_at_the_missing_companion_still_reports_it(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        # `havePairedFile` is cross-file: src/service.py is matched by
        # `paths`, but the convention's companion target
        # (tests/test_service.py) is what's missing. Scoping `--files` to
        # *only* that companion path (as if an agent had just deleted or
        # edited it) must still select and fully evaluate the convention
        # anchored at src/service.py -- not silently report clean.
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-paired-broken"),
            "check",
            "--files",
            "tests/test_service.py",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing paired file: tests/test_service.py" in stdout
        assert "Checked 1 file" in stdout

    def test_unscoped_check_also_reports_the_missing_companion(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "diff-scoped-paired-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing paired file: tests/test_service.py" in stdout


class TestChangedOutsideGitRepo:
    def test_changed_flag_outside_a_git_repo_prints_one_clear_message(
        self,
        tmp_path: Path,
        run_cli,
    ) -> None:
        # No `git init` here: `tmp_path` is a plain directory, not nested
        # under any git work tree. `--changed` must degrade to a single,
        # deliberate error message -- never relay git's raw stderr (which,
        # for `git diff --no-index` falling back on a non-repo, is a
        # multi-line usage/help dump that a human or hook-parsing agent
        # cannot act on).
        (tmp_path / "konpy.json").write_text(
            '{"version": "v1", "conventions": []}\n',
            encoding="utf-8",
        )

        exit_code, _stdout, stderr = run_cli(tmp_path, "check", "--changed")

        assert exit_code == 1
        assert "requires a git repository" in stderr
        assert len(stderr.strip().splitlines()) == 1
        assert "usage:" not in stderr.lower()
