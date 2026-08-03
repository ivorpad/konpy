from __future__ import annotations

import textwrap

from konpy.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "module.py")


class TestDecorators:
    def test_plain_import_alias_decorator(self) -> None:
        result = parse_source(
            """
            import pytest as pt

            @pt.mark.skip
            def test_it(): ...
            """
        )

        assert len(result.decorators) == 1
        decorator = result.decorators[0]
        assert decorator.written == "pt.mark.skip"
        assert decorator.resolved == "pytest.mark.skip"
        assert decorator.is_call is False
        assert decorator.target_kind == "function"
        assert decorator.target_qualified_name == "test_it"

    def test_from_import_alias_call_decorator(self) -> None:
        result = parse_source(
            """
            from pytest import mark as m

            @m.skip(reason="x")
            def test_it(): ...
            """
        )

        assert len(result.decorators) == 1
        decorator = result.decorators[0]
        assert decorator.written == "m.skip"
        assert decorator.resolved == "pytest.mark.skip"
        assert decorator.is_call is True

    def test_unresolved_root_keeps_written_as_resolved(self) -> None:
        result = parse_source(
            """
            def cached(f): return f

            @cached
            def g(): ...
            """
        )

        decorator = result.decorators[0]
        assert decorator.written == "cached"
        assert decorator.resolved == "cached"

    def test_nested_method_decorator_qualified_name(self) -> None:
        result = parse_source(
            """
            class Outer:
                @staticmethod
                def method(): ...
            """
        )

        decorator = result.decorators[0]
        assert decorator.written == "staticmethod"
        assert decorator.target_kind == "function"
        assert decorator.target_qualified_name == "Outer.method"


class TestCallSites:
    def test_module_level_call_scope(self) -> None:
        result = parse_source("Config()")

        assert len(result.call_sites) == 1
        assert result.call_sites[0].scope == "module"
        assert result.call_sites[0].written == "Config"

    def test_call_inside_function_scope(self) -> None:
        result = parse_source(
            """
            def f():
                Config()
            """
        )

        calls = [c for c in result.call_sites if c.written == "Config"]
        assert len(calls) == 1
        assert calls[0].scope == "function"

    def test_call_directly_in_class_body_scope(self) -> None:
        result = parse_source(
            """
            class C:
                Config()
            """
        )

        calls = [c for c in result.call_sites if c.written == "Config"]
        assert len(calls) == 1
        assert calls[0].scope == "class"

    def test_decorator_call_is_also_a_call_site(self) -> None:
        result = parse_source(
            """
            import pytest as pt

            @pt.mark.skip(reason="x")
            def test_it(): ...
            """
        )

        assert len(result.decorators) == 1
        matching = [c for c in result.call_sites if c.written == "pt.mark.skip"]
        assert len(matching) == 1
        assert matching[0].resolved == "pytest.mark.skip"
        assert matching[0].scope == "module"


class TestBaseClassRefs:
    def test_relative_from_import(self) -> None:
        result = parse_source(
            """
            from .utils import helper

            helper()
            """
        )

        calls = [c for c in result.call_sites if c.written == "helper"]
        assert calls[0].resolved == ".utils.helper"

    def test_subscript_base_unwraps_to_unsubscripted_path(self) -> None:
        result = parse_source(
            """
            from typing import Generic, TypeVar

            T = TypeVar("T")

            class Base(Generic[T]): ...

            class A(Base[int]): ...
            """
        )

        refs = {ref.class_qualified_name: ref for ref in result.base_class_refs}
        assert refs["A"].written == "Base"
        assert refs["A"].resolved == "Base"
        assert refs["Base"].written == "Generic"
        assert refs["Base"].resolved == "typing.Generic"

    def test_aliased_base_class(self) -> None:
        result = parse_source(
            """
            from pydantic import BaseModel as BM

            class X(BM): ...
            """
        )

        base = result.base_class_refs[0]
        assert base.written == "BM"
        assert base.resolved == "pydantic.BaseModel"
        assert base.class_qualified_name == "X"


class TestScopedImports:
    def test_module_vs_function_nested_import_scope(self) -> None:
        result = parse_source(
            """
            import os

            def f():
                import json
                return json
            """
        )

        by_source = {entry.source: entry for entry in result.scoped_imports}
        assert by_source["os"].scope == "module"
        assert by_source["json"].scope == "function"

    def test_type_checking_guarded_import_is_type(self) -> None:
        result = parse_source(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                import os
            else:
                import sys
            """
        )

        by_source = {entry.source: entry for entry in result.scoped_imports}
        assert by_source["os"].is_type is True
        assert by_source["sys"].is_type is False

    def test_from_import_multiple_names_two_entries(self) -> None:
        result = parse_source("from pkg import a, b")

        entries = [entry for entry in result.scoped_imports if entry.source == "pkg"]
        assert len(entries) == 2
        assert {entry.symbol_path for entry in entries} == {"pkg.a", "pkg.b"}

    def test_function_nested_import_absent_from_plain_imports_list(self) -> None:
        result = parse_source(
            """
            def f():
                import json
                return json
            """
        )

        assert "json" not in [entry.name for entry in result.imports]
        assert any(entry.source == "json" for entry in result.scoped_imports)
