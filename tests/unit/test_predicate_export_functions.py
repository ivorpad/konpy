from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.export_functions import check_export_functions
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


class TestExportFunctions:
    def test_returns_no_diagnostics_when_exported_function_is_found(self) -> None:
        result = check_export_functions(
            expected=["my_func"],
            context=context(),
            structure=parse_source("def my_func(): pass"),
        )

        assert result == []

    def test_returns_diagnostic_when_function_is_missing(self) -> None:
        result = check_export_functions(
            expected=["my_func"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export function "my_func"'
        assert result[0].predicate_name == "exportFunctions"
        assert result[0].file_path == "src/index.py"
        assert result[0].line is None

    def test_returns_diagnostic_when_function_exists_but_is_not_exported(self) -> None:
        result = check_export_functions(
            expected=["my_func"],
            context=context(),
            structure=parse_source(
                """
                __all__ = []

                def my_func():
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export function "my_func"'

    def test_returns_diagnostic_when_param_type_does_not_match(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "receiveParamOfType": "Request"}],
            context=context(),
            structure=parse_source(
                """
                def my_func(input: str):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" must receive a parameter of type "Request"'
        )
        assert result[0].line == 1

    def test_returns_no_diagnostic_when_param_type_matches(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "receiveParamOfType": "Request"}],
            context=context(),
            structure=parse_source(
                """
                def my_func(req: Request):
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostic_when_ordered_param_types_match(self) -> None:
        result = check_export_functions(
            expected=[
                {
                    "name": "my_func",
                    "receiveParamsOfTypes": ["Request", "Context"],
                }
            ],
            context=context(),
            structure=parse_source(
                """
                def my_func(req: Request, ctx: Context, signal: AbortSignal):
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_when_ordered_param_type_does_not_match(self) -> None:
        result = check_export_functions(
            expected=[
                {
                    "name": "my_func",
                    "receiveParamsOfTypes": ["Request", "Context"],
                }
            ],
            context=context(),
            structure=parse_source(
                """
                def my_func(req: Request, ctx: WrongContext):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" parameter 2 must be of type "Context"'
        )

    def test_returns_diagnostic_when_ordered_param_is_missing(self) -> None:
        result = check_export_functions(
            expected=[
                {
                    "name": "my_func",
                    "receiveParamsOfTypes": ["Request", "Context"],
                }
            ],
            context=context(),
            structure=parse_source(
                """
                def my_func(req: Request):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" parameter 2 must be of type "Context"'
        )

    def test_enforces_deprecated_and_ordered_param_checks_when_both_are_present(self) -> None:
        result = check_export_functions(
            expected=[
                {
                    "name": "my_func",
                    "receiveParamOfType": "LegacyRequest",
                    "receiveParamsOfTypes": ["Request"],
                }
            ],
            context=context(),
            structure=parse_source(
                """
                def my_func(req: Request):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" must receive a parameter of type "LegacyRequest"'
        )

    def test_returns_diagnostic_when_return_type_does_not_match(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "returnValueOfType": "Promise[Response]"}],
            context=context(),
            structure=parse_source(
                """
                def my_func() -> None:
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" must return value of type "Promise[Response]"'
        )
        assert result[0].line == 1

    def test_returns_no_diagnostic_when_return_type_matches(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "returnValueOfType": "None"}],
            context=context(),
            structure=parse_source(
                """
                def my_func() -> None:
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostic_when_bare_config_matches_generic_return(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "returnValueOfType": "MyClass"}],
            context=context(),
            structure=parse_source(
                """
                def my_func() -> MyClass[Foo]:
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostic_when_bare_config_matches_generic_param(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "receiveParamOfType": "MyClass"}],
            context=context(),
            structure=parse_source(
                """
                def my_func(value: MyClass[Foo]):
                    pass
                """
            ),
        )

        assert result == []

    def test_preserves_exact_match_when_configured_return_type_has_generics(self) -> None:
        result = check_export_functions(
            expected=[{"name": "my_func", "returnValueOfType": "Promise[None]"}],
            context=context(),
            structure=parse_source(
                """
                def my_func() -> Promise[str]:
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "my_func" must return value of type "Promise[None]"'
        )

    def test_resolves_templates_in_name_param_type_and_return_type(self) -> None:
        result = check_export_functions(
            expected=[
                {
                    "name": "${action}Handler",
                    "receiveParamOfType": "${action}Request",
                    "returnValueOfType": "${action}Response",
                }
            ],
            context=context({"action": PlaceholderValue("Create")}),
            structure=parse_source(
                """
                def CreateHandler(req: CreateRequest) -> CreateResponse:
                    pass
                """
            ),
        )

        assert result == []

    def test_accepts_string_shorthand_expanding_to_name(self) -> None:
        result = check_export_functions(
            expected=["handler"],
            context=context(),
            structure=parse_source("def handler(): pass"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export_functions(
            expected=["missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="func-exports",
        )

        assert result[0].convention_name == "func-exports"
