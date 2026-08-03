from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_imports import check_restrict_imports
from konpy.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/service.py")


def context() -> PredicateContext:
    return PredicateContext(
        path="src/service.py",
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


def check(source: str, expected: object):
    return check_restrict_imports(
        expected=expected,
        context=context(),
        structure=parse_source(source),
    )


class TestRestrictImportsForbid:
    def test_forbid_hits_on_source(self) -> None:
        result = check("import os", expected={"forbid": ["os"]})

        assert len(result) == 1
        assert result[0].found == "os"

    def test_no_match_is_clean(self) -> None:
        result = check("import os", expected={"forbid": ["sys"]})

        assert result == []

    def test_function_scoped_import_caught(self) -> None:
        # mustNot.importFrom only sees module-level imports; a function-nested
        # import is exactly the case restrictImports exists to catch.
        result = check(
            """
            def f():
                import json
                return json
            """,
            expected={"forbid": ["json"]},
        )

        assert len(result) == 1
        assert result[0].found == "json"
        assert result[0].message == 'Import of "json" is forbidden (function-scoped import)'


class TestRestrictImportsAllow:
    def test_allow_overrides_forbid(self) -> None:
        result = check(
            "from pkg import Logger",
            expected={"forbid": ["pkg.*"], "allow": ["pkg.Logger"]},
        )

        assert result == []


class TestRestrictImportsScope:
    def test_scope_function_only_flags_nested_imports(self) -> None:
        result = check(
            """
            import json

            def f():
                import json as j
                return j
            """,
            expected={"forbid": ["json"], "scope": "function"},
        )

        assert len(result) == 1
        assert result[0].line == 4

    def test_scope_module_only_flags_top_level_imports(self) -> None:
        result = check(
            """
            import json

            def f():
                import json as j
                return j
            """,
            expected={"forbid": ["json"], "scope": "module"},
        )

        assert len(result) == 1
        assert result[0].line == 1

    def test_scope_defaults_to_any(self) -> None:
        result = check(
            """
            import json

            def f():
                import json as j
                return j
            """,
            expected={"forbid": ["json"]},
        )

        assert len(result) == 2


class TestRestrictImportsTypeChecking:
    def test_type_checking_import_skipped_by_default(self) -> None:
        result = check(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                import os
            """,
            expected={"forbid": ["os"]},
        )

        assert result == []

    def test_type_checking_import_caught_with_include_type_checking(self) -> None:
        result = check(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                import os
            """,
            expected={"forbid": ["os"], "includeTypeChecking": True},
        )

        assert len(result) == 1
        assert result[0].found == "os"


class TestRestrictImportsSymbolPath:
    def test_symbol_path_ban_matches_named_import_only(self) -> None:
        result = check(
            """
            from pkg import Logger, Other
            """,
            expected={"forbid": ["pkg.Logger"]},
        )

        assert len(result) == 1
        assert result[0].found == "pkg.Logger"


class TestRestrictImportsDiagnostics:
    def test_diagnostic_fields_and_position(self) -> None:
        result = check("import os", expected={"forbid": ["os"]})

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictImports"
        assert diagnostic.line == 1
        assert diagnostic.column == 1
        assert diagnostic.expected == "no forbidden import"
        assert diagnostic.found == "os"
        assert diagnostic.fix_hint == "Remove the import or import an allowed module instead."
        assert diagnostic.message == 'Import of "os" is forbidden'

    def test_sorted_by_line_column_found_for_multiple_hits(self) -> None:
        result = check(
            """
            import sys
            import os
            """,
            expected={"forbid": ["sys", "os"]},
        )

        assert [d.line for d in result] == [1, 2]
