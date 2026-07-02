from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.export import check_export
from konsistent.predicates.export_constants import check_export_constants
from konsistent.predicates.export_types import check_export_types
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


class TestExport:
    def test_returns_no_diagnostics_when_export_is_found(self) -> None:
        result = check_export(
            expected=["my_func"],
            context=context(),
            structure=parse_source("def my_func(): pass"),
        )

        assert result == []

    def test_returns_diagnostic_when_export_is_missing(self) -> None:
        result = check_export(
            expected=["missing_export"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export "missing_export"'
        assert result[0].predicate_name == "export"
        assert result[0].file_path == "src/index.py"
        assert result[0].line is None
        assert result[0].column is None

    def test_resolves_template_placeholders_in_export_names(self) -> None:
        result = check_export(
            expected=["${providerId}"],
            context=context({"providerId": PlaceholderValue("openai")}),
            structure=parse_source("from .providers import openai"),
        )

        assert result == []

    def test_returns_diagnostic_for_template_expanded_name_when_missing(self) -> None:
        result = check_export(
            expected=["${providerId}"],
            context=context({"providerId": PlaceholderValue("openai")}),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export "openai"'

    def test_accepts_export_definition_object_form(self) -> None:
        result = check_export(
            expected=[{"name": "MY_CONST"}],
            context=context(),
            structure=parse_source("MY_CONST = 1"),
        )

        assert result == []

    def test_ignores_type_only_exports_when_checking_value_exports(self) -> None:
        result = check_export(
            expected=["MyType"],
            context=context(),
            structure=parse_source(
                """
                from typing import TypeAlias

                MyType: TypeAlias = str
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export "MyType"'

    def test_returns_no_diagnostics_when_re_export_with_matching_from_is_found(self) -> None:
        result = check_export(
            expected=[{"name": "helper", "from": ".utils"}],
            context=context(),
            structure=parse_source("from .utils import helper"),
        )

        assert result == []

    def test_returns_diagnostic_when_from_does_not_match(self) -> None:
        result = check_export(
            expected=[{"name": "helper", "from": ".utils"}],
            context=context(),
            structure=parse_source("from .other import helper"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export "helper" from ".utils"'

    def test_resolves_template_placeholders_in_from(self) -> None:
        result = check_export(
            expected=[{"name": "helper", "from": ".${name}"}],
            context=context({"name": PlaceholderValue("utils")}),
            structure=parse_source("from .utils import helper"),
        )

        assert result == []

    def test_does_not_require_from_when_not_specified_in_object_form(self) -> None:
        result = check_export(
            expected=[{"name": "helper"}],
            context=context(),
            structure=parse_source("from .anywhere import helper"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export(
            expected=["missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="barrel-exports",
        )

        assert result[0].convention_name == "barrel-exports"


class TestExportTypes:
    def test_returns_no_diagnostics_when_type_export_is_found(self) -> None:
        result = check_export_types(
            expected=["MyType"],
            context=context(),
            structure=parse_source(
                """
                from typing import TypeAlias

                MyType: TypeAlias = str
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_when_type_export_is_missing(self) -> None:
        result = check_export_types(
            expected=["MyType"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export type "MyType"'
        assert result[0].predicate_name == "exportTypes"

    def test_ignores_non_type_exports(self) -> None:
        result = check_export_types(
            expected=["my_func"],
            context=context(),
            structure=parse_source("def my_func(): pass"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export type "my_func"'

    def test_resolves_template_placeholders(self) -> None:
        result = check_export_types(
            expected=["${name}Props"],
            context=context({"name": PlaceholderValue("Button")}),
            structure=parse_source(
                """
                from typing import TypeAlias

                ButtonProps: TypeAlias = dict
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_for_template_expanded_name_when_missing(self) -> None:
        result = check_export_types(
            expected=["${name}Props"],
            context=context({"name": PlaceholderValue("Button")}),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export type "ButtonProps"'

    def test_accepts_export_definition_object_form(self) -> None:
        result = check_export_types(
            expected=[{"name": "Config"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TypeAlias

                Config: TypeAlias = dict
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostics_when_type_re_export_matching_from_is_found(self) -> None:
        result = check_export_types(
            expected=[{"name": "MyType", "from": ".types"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .types import MyType
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_when_type_export_from_does_not_match(self) -> None:
        result = check_export_types(
            expected=[{"name": "MyType", "from": ".types"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .other import MyType
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export type "MyType" from ".types"'

    def test_resolves_template_placeholders_in_type_export_from(self) -> None:
        result = check_export_types(
            expected=[{"name": "MyType", "from": ".${name}"}],
            context=context({"name": PlaceholderValue("types")}),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .types import MyType
                """
            ),
        )

        assert result == []

    def test_does_not_require_from_when_not_specified_in_object_form(self) -> None:
        result = check_export_types(
            expected=[{"name": "MyType"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .anywhere import MyType
                """
            ),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export_types(
            expected=["Missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="type-exports",
        )

        assert result[0].convention_name == "type-exports"


class TestExportConstants:
    def test_returns_no_diagnostics_when_exported_constant_is_found(self) -> None:
        result = check_export_constants(
            expected=["MY_CONST"],
            context=context(),
            structure=parse_source("MY_CONST = 1"),
        )

        assert result == []

    def test_returns_diagnostic_when_exported_constant_is_missing(self) -> None:
        result = check_export_constants(
            expected=["MY_CONST"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export constant "MY_CONST"'
        assert result[0].predicate_name == "exportConstants"

    def test_ignores_non_const_exports(self) -> None:
        result = check_export_constants(
            expected=["my_func"],
            context=context(),
            structure=parse_source("def my_func(): pass"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export constant "my_func"'

    def test_ignores_type_exports_of_constant_names(self) -> None:
        result = check_export_constants(
            expected=["MY_CONST"],
            context=context(),
            structure=parse_source(
                """
                from typing import TypeAlias

                MY_CONST: TypeAlias = int
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export constant "MY_CONST"'

    def test_resolves_template_placeholders(self) -> None:
        result = check_export_constants(
            expected=["${prefix}_CONFIG"],
            context=context({"prefix": PlaceholderValue("APP")}),
            structure=parse_source("APP_CONFIG = 1"),
        )

        assert result == []

    def test_returns_diagnostic_for_template_expanded_name_when_missing(self) -> None:
        result = check_export_constants(
            expected=["${prefix}_CONFIG"],
            context=context({"prefix": PlaceholderValue("APP")}),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export constant "APP_CONFIG"'

    def test_accepts_export_definition_object_form(self) -> None:
        result = check_export_constants(
            expected=[{"name": "MY_CONST"}],
            context=context(),
            structure=parse_source("MY_CONST = 1"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export_constants(
            expected=["missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="const-exports",
        )

        assert result[0].convention_name == "const-exports"
