from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_calls import check_restrict_calls
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
    return check_restrict_calls(
        expected=expected,
        context=context(),
        structure=parse_source(source),
    )


class TestRestrictCallsForbid:
    def test_forbid_hits_on_written_form(self) -> None:
        result = check(
            """
            def cached(): ...

            cached()
            """,
            expected={"forbid": ["cached"]},
        )

        assert len(result) == 1
        assert result[0].found == "cached"

    def test_forbid_hits_on_resolved_form_through_aliased_import(self) -> None:
        result = check(
            """
            import subprocess as sp

            sp.run("x")
            """,
            expected={"forbid": ["subprocess.run"]},
        )

        assert len(result) == 1
        assert result[0].found == "sp.run"

    def test_no_match_is_clean(self) -> None:
        result = check(
            """
            import subprocess as sp

            sp.run("x")
            """,
            expected={"forbid": ["os.system"]},
        )

        assert result == []


class TestRestrictCallsAllow:
    def test_allow_overrides_forbid(self) -> None:
        result = check(
            """
            import subprocess

            subprocess.run("x")
            """,
            expected={"forbid": ["subprocess.*"], "allow": ["subprocess.run"]},
        )

        assert result == []


class TestRestrictCallsScope:
    def test_scope_module_catches_module_and_class_body_calls_not_function_body(self) -> None:
        result = check(
            """
            import subprocess

            class Config:
                subprocess.run("class-body")

            def f():
                subprocess.run("function-body")

            subprocess.run("module-body")
            """,
            expected={"forbid": ["subprocess.run"], "scope": "module"},
        )

        assert len(result) == 2
        assert [d.line for d in result] == [4, 9]

    def test_scope_any_catches_all(self) -> None:
        result = check(
            """
            import subprocess

            class Config:
                subprocess.run("class-body")

            def f():
                subprocess.run("function-body")

            subprocess.run("module-body")
            """,
            expected={"forbid": ["subprocess.run"], "scope": "any"},
        )

        assert len(result) == 3
        assert [d.line for d in result] == [4, 7, 9]

    def test_scope_defaults_to_any(self) -> None:
        result = check(
            """
            import subprocess

            def f():
                subprocess.run("function-body")
            """,
            expected={"forbid": ["subprocess.run"]},
        )

        assert len(result) == 1


class TestRestrictCallsDiagnostics:
    def test_diagnostic_fields_and_position(self) -> None:
        result = check(
            """
            import subprocess as sp

            sp.run("x")
            """,
            expected={"forbid": ["subprocess.run"]},
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictCalls"
        assert diagnostic.line == 3
        assert diagnostic.expected == "no forbidden call"
        assert diagnostic.found == "sp.run"
        assert diagnostic.fix_hint == "Remove the call to sp.run or move it behind an allowed seam."
        assert diagnostic.message == (
            'Call to "sp.run" is forbidden (resolves to "subprocess.run")'
        )

    def test_module_scope_diagnostic_message_and_fix_hint(self) -> None:
        result = check(
            """
            import subprocess

            subprocess.run("x")
            """,
            expected={"forbid": ["subprocess.run"], "scope": "module"},
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.message == 'Call to "subprocess.run" is forbidden at module scope'
        assert diagnostic.fix_hint == (
            "Defer this call into a function so it does not run at import time."
        )

    def test_sorted_by_line_column_found_for_multiple_hits(self) -> None:
        result = check(
            """
            import subprocess

            subprocess.run("b")
            subprocess.run("a")
            """,
            expected={"forbid": ["subprocess.run"]},
        )

        assert [d.line for d in result] == [3, 4]
