from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.import_source import check_import_source
from konpy.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/index.py")


def context() -> PredicateContext:
    return PredicateContext(
        path="src/index.py",
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestImportSource:
    def test_requires_imports_from_the_current_directory(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("from .helper import helper"),
        )

        assert result == []

    def test_accepts_bare_current_directory_imports(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("from . import helper"),
        )

        assert result == []

    def test_rejects_forbidden_imports_from_the_current_directory(self) -> None:
        result = check_import_source(
            expected=False,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("from . import setup"),
        )

        assert len(result) == 1
        assert result[0].message == "Import from current directory is not allowed"
        assert result[0].line == 1
        assert result[0].column == 1

    def test_matches_imports_from_parents(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromParents",
            group="parents",
            import_kind="value",
            context=context(),
            structure=parse_source("from ..parent import parent"),
        )

        assert result == []

    def test_matches_imports_from_grandparents_as_parent_imports(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromParents",
            group="parents",
            import_kind="value",
            context=context(),
            structure=parse_source("from ...grandparent import value"),
        )

        assert result == []

    def test_ignores_type_imports_for_value_import_source_predicates(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromParents",
            group="parents",
            import_kind="value",
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from ..parent import Parent
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == "Missing import from parent directories"

    def test_matches_type_imports_from_parents(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importTypesFromParents",
            group="parents",
            import_kind="type",
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from ..parent import Parent
                """
            ),
        )

        assert result == []

    def test_ignores_value_imports_for_type_import_source_predicates(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importTypesFromCurrentDir",
            group="currentDir",
            import_kind="type",
            context=context(),
            structure=parse_source("from .helper import helper"),
        )

        assert len(result) == 1
        assert result[0].message == "Missing type import from current directory"

    def test_rejects_forbidden_type_imports_from_externals(self) -> None:
        result = check_import_source(
            expected=False,
            predicate_name="importTypesFromExternals",
            group="externals",
            import_kind="type",
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from zod import ZodType
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == "Type import from external packages is not allowed"
        assert result[0].line == 4
        assert result[0].column == 5

    def test_reports_missing_parent_imports(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromParents",
            group="parents",
            import_kind="value",
            context=context(),
            structure=parse_source("from .helper import helper"),
        )

        assert len(result) == 1
        assert result[0].message == "Missing import from parent directories"

    def test_matches_external_imports(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromExternals",
            group="externals",
            import_kind="value",
            context=context(),
            structure=parse_source(
                """
                import react
                from pathlib import Path
                from scope.pkg import scoped
                """
            ),
        )

        assert result == []

    def test_rejects_forbidden_external_imports(self) -> None:
        result = check_import_source(
            expected=False,
            predicate_name="importFromExternals",
            group="externals",
            import_kind="value",
            context=context(),
            structure=parse_source("import react"),
        )

        assert len(result) == 1
        assert result[0].message == "Import from external packages is not allowed"
        assert result[0].line == 1
        assert result[0].column == 1

    def test_reports_missing_type_imports_from_external_packages(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importTypesFromExternals",
            group="externals",
            import_kind="type",
            context=context(),
            structure=parse_source("import react"),
        )

        assert len(result) == 1
        assert result[0].message == "Missing type import from external packages"

    def test_rejects_forbidden_missing_current_dir_import_requirement(self) -> None:
        result = check_import_source(
            expected=False,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("import react"),
        )

        assert result == []

    def test_missing_import_diagnostic_includes_expected_and_fix_hint(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("import react"),
        )

        assert result[0].expected is not None
        assert "current directory" in result[0].expected
        assert result[0].fix_hint is not None
        assert "from .module import Name" in result[0].fix_hint

    def test_forbidden_import_diagnostic_includes_expected_and_found(self) -> None:
        result = check_import_source(
            expected=False,
            predicate_name="importFromCurrentDir",
            group="currentDir",
            import_kind="value",
            context=context(),
            structure=parse_source("from . import setup"),
        )

        assert result[0].found == "."
        assert result[0].expected is not None
        assert "not allowed" in result[0].message

    def test_type_only_example_mentions_type_checking(self) -> None:
        result = check_import_source(
            expected=True,
            predicate_name="importTypesFromExternals",
            group="externals",
            import_kind="type",
            context=context(),
            structure=parse_source("import react"),
        )

        assert result[0].fix_hint is not None
        assert "TYPE_CHECKING" in result[0].fix_hint
