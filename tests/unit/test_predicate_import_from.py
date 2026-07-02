from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.import_from import check_import_from
from konsistent.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/index.py")


def context(
    placeholders: dict[str, PlaceholderValue] | None = None,
) -> PredicateContext:
    return PredicateContext(
        path="src/index.py",
        placeholders=placeholders or {},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestImportFrom:
    def test_matches_exact_relative_import_sources(self) -> None:
        result = check_import_from(
            expected=".helper",
            context=context(),
            structure=parse_source("from .helper import value"),
        )

        assert result == []

    def test_returns_a_diagnostic_when_the_import_source_is_missing(self) -> None:
        result = check_import_from(
            expected=".helper",
            context=context(),
            structure=parse_source("from .setup import value"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import from ".helper"'
        assert result[0].predicate_name == "importFrom"
        assert result[0].file_path == "src/index.py"

    def test_matches_absolute_dotted_submodules_from_package_root(self) -> None:
        result = check_import_from(
            expected="react",
            context=context(),
            structure=parse_source("from react.jsx_runtime import jsx"),
        )

        assert result == []

    def test_matches_absolute_dotted_submodules_from_dotted_package_root(self) -> None:
        result = check_import_from(
            expected="scope.pkg",
            context=context(),
            structure=parse_source("from scope.pkg.tools import tool"),
        )

        assert result == []

    def test_does_not_match_similarly_named_absolute_packages(self) -> None:
        result = check_import_from(
            expected="react",
            context=context(),
            structure=parse_source("from react_dom import render"),
        )

        assert len(result) == 1

    def test_treats_relative_expected_values_as_exact_sources(self) -> None:
        result = check_import_from(
            expected=".helper",
            context=context(),
            structure=parse_source("from .helper.sub import value"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import from ".helper"'

    def test_treats_parent_relative_expected_values_as_exact_sources(self) -> None:
        result = check_import_from(
            expected="..parent",
            context=context(),
            structure=parse_source("from ..parent.sub import value"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import from "..parent"'

    def test_matches_type_only_import_statements(self) -> None:
        result = check_import_from(
            expected="scope.pkg",
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from scope.pkg import Tool
                """
            ),
        )

        assert result == []

    def test_resolves_template_placeholders_in_the_source(self) -> None:
        result = check_import_from(
            expected="scope.${packageName}",
            context=context({"packageName": PlaceholderValue("pkg")}),
            structure=parse_source("from scope.pkg.tools import tool"),
        )

        assert result == []

    def test_resolves_templates_for_dotted_relative_sources(self) -> None:
        result = check_import_from(
            expected=".${moduleName}",
            context=context({"moduleName": PlaceholderValue("helper")}),
            structure=parse_source("from .helper import value"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_import_from(
            expected="react",
            context=context(),
            structure=parse_source(""),
            convention_name="react-files",
        )

        assert result[0].convention_name == "react-files"
