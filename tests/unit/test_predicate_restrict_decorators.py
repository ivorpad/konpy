from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_decorators import check_restrict_decorators
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
    return check_restrict_decorators(
        expected=expected,
        context=context(),
        structure=parse_source(source),
    )


class TestRestrictDecoratorsForbid:
    def test_forbid_hits_on_written_form(self) -> None:
        result = check(
            """
            def cached(f): return f

            @cached
            def g(): ...
            """,
            expected={"forbid": ["cached"]},
        )

        assert len(result) == 1
        assert result[0].found == "@cached"

    def test_forbid_hits_on_resolved_form_through_aliased_import(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.skip
            def test_it(): ...
            """,
            expected={"forbid": ["pytest.mark.*"]},
        )

        assert len(result) == 1
        assert result[0].found == "@pt.mark.skip"

    def test_no_match_is_clean(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.skip
            def test_it(): ...
            """,
            expected={"forbid": ["unittest.*"]},
        )

        assert result == []


class TestRestrictDecoratorsAllow:
    def test_allow_overrides_forbid(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.skip
            def test_it(): ...
            """,
            expected={"forbid": ["pytest.mark.*"], "allow": ["pt.mark.skip"]},
        )

        assert result == []


class TestRestrictDecoratorsTargets:
    def test_decorator_with_arguments_is_a_call(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.skip(reason="x")
            def test_it(): ...
            """,
            expected={"forbid": ["pytest.mark.*"]},
        )

        assert len(result) == 1
        assert "test_it" in result[0].message

    def test_method_of_nested_class_qualified_name(self) -> None:
        result = check(
            """
            class Outer:
                @staticmethod
                def method(): ...
            """,
            expected={"forbid": ["staticmethod"]},
        )

        assert len(result) == 1
        assert 'on function "Outer.method"' in result[0].message


class TestRestrictDecoratorsDiagnostics:
    def test_diagnostic_fields_and_position(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.skip
            def test_it(): ...
            """,
            expected={"forbid": ["pytest.mark.*"]},
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictDecorators"
        assert diagnostic.line == 3
        assert diagnostic.column == 2
        assert diagnostic.expected == "no forbidden decorator"
        assert diagnostic.found == "@pt.mark.skip"
        assert diagnostic.fix_hint == "Remove @pt.mark.skip or use an allowed alternative."
        assert diagnostic.message == (
            'Decorator "@pt.mark.skip" on function "test_it" is forbidden '
            '(resolves to "pytest.mark.skip")'
        )

    def test_sorted_by_line_column_found_for_multiple_hits(self) -> None:
        result = check(
            """
            import pytest as pt

            @pt.mark.slow
            def b(): ...

            @pt.mark.skip
            def a(): ...
            """,
            expected={"forbid": ["pytest.mark.*"]},
        )

        assert [d.line for d in result] == [3, 6]
        assert [d.found for d in result] == ["@pt.mark.slow", "@pt.mark.skip"]
