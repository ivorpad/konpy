from __future__ import annotations

from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestDeclarationPredicatesFixture:
    def test_check_exits_zero_when_all_local_declarations_pass(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "declaration-predicates"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout


class TestDeclarationPredicatesBrokenFixture:
    def test_check_exits_one_with_declaration_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "declaration-predicates-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Local type declaration "LocalType" must not be exported' in stdout
        assert 'Local function declaration "createLocal" must not be exported' in stdout
        assert "local-declarations" in stdout


class TestDeclarationOrderFixture:
    def test_check_exits_zero_when_declarations_are_ordered(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "declaration-order"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout


class TestDeclarationOrderBrokenFixture:
    def test_check_exits_one_with_declaration_order_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "declaration-order-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Symbol "alpha" must be declared before "Beta"' in stdout
        assert "declarations-in-order" in stdout


class TestImportSourceGroupsFixture:
    def test_check_exits_zero_when_import_source_groups_pass(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "import-source-groups"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout


class TestImportSourceGroupsBrokenFixture:
    def test_check_exits_one_with_import_source_group_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "import-source-groups-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert "Missing import from current directory" in stdout
        assert "Import from parent directories is not allowed" in stdout
        assert "Missing import from external packages" in stdout
        assert "Import from current directory is not allowed" in stdout
        assert "Missing type import from current directory" in stdout
        assert "Type import from parent directories is not allowed" in stdout
        assert "Missing type import from external packages" in stdout
        assert "Type import from current directory is not allowed" in stdout


class TestImportFromFixture:
    def test_check_exits_zero_when_import_from_predicates_pass(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "import-from"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout


class TestImportFromBrokenFixture:
    def test_check_exits_one_with_import_from_violations(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "import-from-broken"),
            "check",
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Missing import from ".helper"' in stdout
        assert 'Missing import from "scope.pkg"' in stdout
        assert 'Forbidden import from "react"' in stdout


class TestTypeCheckingImportsFixture:
    def test_check_exits_zero_for_type_imports_inside_type_checking_blocks(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "type-checking-imports"),
            "check",
        )

        assert exit_code == 0
        assert stderr == ""
        assert "No violations found." in stdout

    def test_reverse_config_flags_type_imports_from_type_checking_blocks(
        self,
        fixtures_dir: Path,
        run_cli,
    ) -> None:
        fixture = _fixture(fixtures_dir, "type-checking-imports")
        exit_code, stdout, stderr = run_cli(
            fixture,
            "check",
            "--config-path",
            str(fixture / "konpy-reverse.json"),
        )

        assert exit_code == 1
        assert stderr == ""
        assert 'Forbidden type import "LocalModel"' in stdout
        assert 'Forbidden type import "SharedConfig"' in stdout
        assert 'Forbidden type import "Mapping"' in stdout
        assert "Forbidden type import from current directory" in stdout
        assert "Forbidden type import from parent directories" in stdout
        assert "Forbidden type import from external packages" in stdout

