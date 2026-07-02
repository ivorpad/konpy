from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestBarrelFilesFixture:
    def test_check_exits_zero_when_init_only_reexports(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "barrel-files"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_validate_accepts_are_barrel_files_predicate(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "barrel-files"),
            "validate",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "Configuration is valid." in stdout


class TestBarrelFilesBrokenFixture:
    def test_check_exits_one_when_init_declares_a_constant(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "barrel-files-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Barrel file must not contain declarations" in stdout
        assert "barrels-must-be-pure" in stdout
        assert "Found 1 error." in stdout

