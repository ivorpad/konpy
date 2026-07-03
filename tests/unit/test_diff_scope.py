from __future__ import annotations

import subprocess
from pathlib import Path

from konpy.config.errors import Err, Ok
from konpy.core.diff_scope import compute_changed_files, resolve_diff_scope


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
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_resolve_diff_scope_returns_none_when_neither_flag_given(tmp_path: Path) -> None:
    result = resolve_diff_scope(files=None, changed=False, cwd=tmp_path)

    assert result == Ok(None)


def test_resolve_diff_scope_files_normalizes_relative_paths(tmp_path: Path) -> None:
    result = resolve_diff_scope(files=["./src/a.py", "src/b.py/"], changed=False, cwd=tmp_path)

    assert isinstance(result, Ok)
    assert result.value == frozenset({"src/a.py", "src/b.py"})


def test_resolve_diff_scope_files_normalizes_absolute_paths_under_cwd(tmp_path: Path) -> None:
    result = resolve_diff_scope(
        files=[str(tmp_path / "src/a.py")],
        changed=False,
        cwd=tmp_path,
    )

    assert isinstance(result, Ok)
    assert result.value == frozenset({"src/a.py"})


def test_resolve_diff_scope_files_leaves_absolute_paths_outside_cwd_as_is(
    tmp_path: Path,
) -> None:
    result = resolve_diff_scope(files=["/etc/other/a.py"], changed=False, cwd=tmp_path)

    assert isinstance(result, Ok)
    assert result.value == frozenset({"/etc/other/a.py"})


def test_resolve_diff_scope_rejects_files_and_changed_together(tmp_path: Path) -> None:
    result = resolve_diff_scope(files=["a.py"], changed=True, cwd=tmp_path)

    assert isinstance(result, Err)
    assert "--files" in result.error
    assert "--changed" in result.error


def test_resolve_diff_scope_changed_invokes_git_diff_and_ls_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "modified.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "modified.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add modified.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "modified.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("VALUE = 3\n", encoding="utf-8")

    result = resolve_diff_scope(files=None, changed=True, cwd=tmp_path)

    assert isinstance(result, Ok)
    assert result.value == frozenset({"modified.py", "untracked.py"})


def test_resolve_diff_scope_changed_returns_empty_set_when_nothing_changed(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)

    result = resolve_diff_scope(files=None, changed=True, cwd=tmp_path)

    assert result == Ok(frozenset())


def test_resolve_diff_scope_changed_errors_when_not_a_git_repo(tmp_path: Path) -> None:
    result = resolve_diff_scope(files=None, changed=True, cwd=tmp_path)

    assert isinstance(result, Err)
    assert "git" in result.error.lower()


def test_resolve_diff_scope_changed_errors_when_git_binary_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_run(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = resolve_diff_scope(files=None, changed=True, cwd=tmp_path)

    assert isinstance(result, Err)


def test_compute_changed_files_dedupes_and_orders_diff_before_untracked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeCompleted:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def fake_run(args: list[str], **kwargs: object) -> FakeCompleted:
        if "diff" in args:
            return FakeCompleted("shared.py\nmodified.py\nshared.py\n")
        return FakeCompleted("untracked.py\nshared.py\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = compute_changed_files(cwd=tmp_path)

    assert isinstance(result, Ok)
    assert result.value == ["shared.py", "modified.py", "untracked.py"]
