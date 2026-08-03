from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_base_classes import check_restrict_base_classes
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
    return check_restrict_base_classes(
        expected=expected,
        context=context(),
        structure=parse_source(source),
    )


class TestRestrictBaseClassesForbid:
    def test_forbid_hits_on_written_form(self) -> None:
        result = check(
            """
            class Base: ...

            class X(Base): ...
            """,
            expected={"forbid": ["Base"]},
        )

        assert len(result) == 1
        assert result[0].found == "Base"

    def test_forbid_hits_on_resolved_form_through_aliased_import(self) -> None:
        result = check(
            """
            from pydantic import BaseModel as BM

            class X(BM): ...
            """,
            expected={"forbid": ["pydantic.BaseModel"]},
        )

        assert len(result) == 1
        assert result[0].found == "BM"

    def test_no_match_is_clean(self) -> None:
        result = check(
            """
            from pydantic import BaseModel as BM

            class X(BM): ...
            """,
            expected={"forbid": ["object"]},
        )

        assert result == []


class TestRestrictBaseClassesAllow:
    def test_allow_overrides_forbid(self) -> None:
        result = check(
            """
            from pydantic import BaseModel as BM

            class X(BM): ...
            """,
            expected={"forbid": ["pydantic.*"], "allow": ["BM"]},
        )

        assert result == []


class TestRestrictBaseClassesTargets:
    def test_subscripted_base_unwraps_to_unsubscripted_path(self) -> None:
        result = check(
            """
            from typing import Generic, TypeVar

            T = TypeVar("T")

            class A(Generic[T]): ...
            """,
            expected={"forbid": ["typing.Generic"]},
        )

        assert len(result) == 1
        assert result[0].found == "Generic"
        assert result[0].message == (
            'Base class "Generic" of class "A" is forbidden (resolves to "typing.Generic")'
        )


class TestRestrictBaseClassesDiagnostics:
    def test_diagnostic_fields_and_position(self) -> None:
        result = check(
            """
            from pydantic import BaseModel as BM

            class X(BM): ...
            """,
            expected={"forbid": ["pydantic.BaseModel"]},
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictBaseClasses"
        assert diagnostic.line == 3
        assert diagnostic.column == 9
        assert diagnostic.expected == "no forbidden base class"
        assert diagnostic.found == "BM"
        assert diagnostic.fix_hint == (
            "Inherit from an allowed base or compose instead of subclassing BM."
        )
        assert diagnostic.message == (
            'Base class "BM" of class "X" is forbidden (resolves to "pydantic.BaseModel")'
        )

    def test_sorted_by_line_column_found_for_multiple_hits(self) -> None:
        result = check(
            """
            from pydantic import BaseModel

            class A(BaseModel): ...

            class B(BaseModel): ...
            """,
            expected={"forbid": ["BaseModel"]},
        )

        assert [d.line for d in result] == [3, 5]
