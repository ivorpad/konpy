from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.predicates.are_barrel_files import check_are_barrel_files
from konsistent.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/index.py")


def context() -> PredicateContext:
    return PredicateContext(
        path="src/index.py",
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestAreBarrelFiles:
    def test_returns_no_diagnostics_when_expected_is_false(self) -> None:
        result = check_are_barrel_files(
            expected=False,
            context=context(),
            structure=parse_source(
                """
                def fn():
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostics_when_file_has_no_non_barrel_statements(self) -> None:
        result = check_are_barrel_files(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                from .module import Imported
                __all__ = ["Alias"]
                Alias = Imported
                """
            ),
        )

        assert result == []

    def test_emits_one_diagnostic_per_non_barrel_statement(self) -> None:
        result = check_are_barrel_files(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                def fn():
                    pass

                call()
                """
            ),
        )

        assert len(result) == 2
        assert result[0].predicate_name == "areBarrelFiles"
        assert result[0].file_path == "src/index.py"
        assert result[0].line == 1
        assert result[0].column == 1
        assert result[0].message == "Barrel file must not contain declarations"
        assert result[1].line == 4
        assert (
            result[1].message
            == "Barrel file must not contain top-level expression statements"
        )

    def test_uses_kind_specific_messages_for_python_taxonomy(self) -> None:
        result = check_are_barrel_files(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                VALUE = 1
                call()
                """
            ),
        )

        assert [diagnostic.message for diagnostic in result] == [
            "Barrel file must not contain declarations",
            "Barrel file must not contain top-level expression statements",
        ]

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_are_barrel_files(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                def fn():
                    pass
                """
            ),
            convention_name="barrel-only",
        )

        assert result[0].convention_name == "barrel-only"
