"""End-to-end coverage for the agent cold-start path: bare help, init, docs."""

from __future__ import annotations

from pathlib import Path


class TestBareInvocation:
    def test_bare_konpy_runs_the_report_and_exits_zero(self, tmp_path: Path, run_cli) -> None:
        exit_code, stdout, _ = run_cli(tmp_path)

        assert exit_code == 0
        assert "konpy report" in stdout
        assert "no konpy.json found" in stdout
        assert "Coverage" in stdout

    def test_help_command_still_prints_the_full_help(self, tmp_path: Path, run_cli) -> None:
        exit_code, stdout, _ = run_cli(tmp_path, "help")

        assert exit_code == 0
        assert "Getting started:" in stdout
        assert '"version": "v1"' in stdout


class TestInitToCheckRoundTrip:
    def test_strict_starter_demands_src_layout_then_passes_once_conforming(
        self, tmp_path: Path, run_cli
    ) -> None:
        init_exit, init_stdout, _ = run_cli(tmp_path, "init")

        assert init_exit == 0
        assert "Wrote konpy.json" in init_stdout
        assert (tmp_path / "konpy.json").is_file()

        bare_exit, bare_stdout, _ = run_cli(tmp_path, "check")

        assert bare_exit == 1
        assert "project-root-uses-src-layout" in bare_stdout

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        package = tmp_path / "src" / "demo"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            '"""Demo package: public API re-exports."""\n\n'
            "from demo.core import add as add\n",
            encoding="utf-8",
        )
        (package / "core.py").write_text(
            '"""Core arithmetic."""\n\n__all__ = ["add"]\n\n\n'
            "def add(left: int, right: int) -> int:\n"
            '    """Return the sum of left and right."""\n'
            "    return left + right\n",
            encoding="utf-8",
        )
        tests_package = tmp_path / "tests" / "demo"
        tests_package.mkdir(parents=True)
        (tests_package / "test_core.py").write_text(
            '"""Tests for demo.core."""\n\nfrom demo.core import add\n\n\n'
            "def test_add() -> None:\n"
            '    """add sums integers."""\n'
            "    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )

        check_exit, check_stdout, _ = run_cli(tmp_path, "check")

        assert check_exit == 0
        assert "No violations found" in check_stdout

    def test_business_logic_in_init_file_fails_the_starter(
        self, tmp_path: Path, run_cli
    ) -> None:
        run_cli(tmp_path, "init")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        package = tmp_path / "src" / "demo"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            '"""Demo package."""\n\n\n'
            "def busy(x: int) -> int:\n"
            '    """Business logic hiding in the barrel."""\n'
            "    return x * 2\n",
            encoding="utf-8",
        )

        exit_code, stdout, _ = run_cli(tmp_path, "check")

        assert exit_code == 1
        assert "init-files-are-barrels" in stdout

    def test_second_init_refuses_and_exits_one(self, tmp_path: Path, run_cli) -> None:
        run_cli(tmp_path, "init")
        exit_code, _, stderr = run_cli(tmp_path, "init")

        assert exit_code == 1
        assert "already exists" in stderr


class TestDocsCommand:
    def test_docs_lists_topics(self, tmp_path: Path, run_cli) -> None:
        exit_code, stdout, _ = run_cli(tmp_path, "docs")

        assert exit_code == 0
        assert "predicates" in stdout

    def test_docs_prints_a_topic(self, tmp_path: Path, run_cli) -> None:
        exit_code, stdout, _ = run_cli(tmp_path, "docs", "cli")

        assert exit_code == 0
        assert stdout.startswith("# CLI")
