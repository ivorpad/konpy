from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


def _check_reverse(run_cli, fixture: Path) -> tuple[int, str, str]:
    return run_cli(
        fixture,
        "check",
        "--config-path",
        str(fixture / "konsistent-reverse.json"),
    )


class TestMustNotReverseConfigs:
    def test_plugin_system_fails_when_files_and_exports_are_present(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "plugin-system"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Forbidden path type "directory"' in stdout
        assert 'Forbidden file "index.py"' in stdout
        assert 'Forbidden file "manifest.json"' in stdout
        assert 'Forbidden file "README.md"' in stdout
        assert 'Forbidden export "activate"' in stdout
        assert 'Forbidden constant export "plugin_id"' in stdout

    def test_ai_toolkit_fails_when_exports_and_type_imports_are_present(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "ai-toolkit"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Forbidden export "openai"' in stdout
        assert 'Forbidden type export "OpenaiProvider"' in stdout
        assert 'Forbidden type import "ProviderV1"' in stdout

    def test_declaration_predicates_fail_for_local_declarations_and_pass_for_exported(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "declaration-predicates"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Forbidden type declaration "LocalType"' in stdout
        assert 'Forbidden function declaration "createLocal"' in stdout

        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "declaration-predicates-broken"),
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_declaration_order_fails_for_matching_order_and_passes_for_broken_order(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "declaration-order"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Forbidden declaration order "alpha", "Beta", "gamma", "missing"' in stdout

        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "declaration-order-broken"),
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_import_source_groups_fail_when_present_and_pass_when_absent(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "import-source-groups"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Forbidden import from current directory" in stdout
        assert "Forbidden import from parent directories" in stdout
        assert "Forbidden import from external packages" in stdout
        assert "Forbidden type import from current directory" in stdout
        assert "Forbidden type import from parent directories" in stdout
        assert "Forbidden type import from external packages" in stdout

        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "import-source-groups-broken"),
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_barrel_files_fail_for_pure_barrels_and_pass_for_non_barrels(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "barrel-files"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Forbidden barrel file" in stdout

        exit_code, stdout, stderr = _check_reverse(
            run_cli,
            _fixture(fixtures_dir, "barrel-files-broken"),
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

