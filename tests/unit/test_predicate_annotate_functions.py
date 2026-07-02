from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.predicates.annotate_functions import check_annotate_functions
from konsistent.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/service.py")


def context() -> PredicateContext:
    return PredicateContext(
        path="src/service.py",
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestAnnotateFunctions:
    def test_returns_no_diagnostics_when_selected_functions_are_fully_annotated(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self, value: str) -> str:
                        return value

                def create_service(name: str) -> Service:
                    return Service()
                """
            ),
        )

        assert result == []

    def test_reports_missing_parameter_and_return_annotations(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self, value):
                        return value

                def create_service(name):
                    return Service()
                """
            ),
        )

        assert [(item.message, item.line, item.column) for item in result] == [
            (
                'Function "Service.run" parameter "value" must have a type annotation',
                2,
                5,
            ),
            ('Function "Service.run" must have a return type annotation', 2, 5),
            (
                'Function "create_service" parameter "name" must have a type annotation',
                5,
                1,
            ),
            ('Function "create_service" must have a return type annotation', 5, 1),
        ]
        assert all(item.predicate_name == "annotateFunctions" for item in result)

    def test_returns_option_false_disables_return_checks(self) -> None:
        result = check_annotate_functions(
            expected={"returns": False, "params": True},
            context=context(),
            structure=parse_source(
                """
                def create_service(name: str):
                    return object()
                """
            ),
        )

        assert result == []

    def test_params_option_false_disables_parameter_checks(self) -> None:
        result = check_annotate_functions(
            expected={"returns": True, "params": False},
            context=context(),
            structure=parse_source(
                """
                def create_service(name) -> object:
                    return object()
                """
            ),
        )

        assert result == []

    def test_public_only_skips_private_functions_and_methods(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Public:
                    def run(self, value):
                        return value

                    def _helper(self, value):
                        return value

                class _Private:
                    def run(self, value):
                        return value

                def public_func(value):
                    return value

                def _private_func(value):
                    return value
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "Public.run" parameter "value" must have a type annotation',
            'Function "Public.run" must have a return type annotation',
            'Function "public_func" parameter "value" must have a type annotation',
            'Function "public_func" must have a return type annotation',
        ]

    def test_public_only_false_includes_private_functions_and_methods(self) -> None:
        result = check_annotate_functions(
            expected={"publicOnly": False},
            context=context(),
            structure=parse_source(
                """
                class Public:
                    def _helper(self, value):
                        return value

                def _private_func(value):
                    return value
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "Public._helper" parameter "value" must have a type annotation',
            'Function "Public._helper" must have a return type annotation',
            'Function "_private_func" parameter "value" must have a type annotation',
            'Function "_private_func" must have a return type annotation',
        ]

    def test_checks_async_keyword_only_varargs_and_kwargs(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                async def fetch(item_id: int, *items, timeout, **kwargs) -> str:
                    return ""
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "fetch" parameter "items" must have a type annotation',
            'Function "fetch" parameter "timeout" must have a type annotation',
            'Function "fetch" parameter "kwargs" must have a type annotation',
        ]

    def test_literal_all_controls_public_annotation_targets(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                __all__ = ["exported"]

                def exported(value):
                    return value

                def hidden(value):
                    return value
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "exported" parameter "value" must have a type annotation',
            'Function "exported" must have a return type annotation',
        ]

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                def create_service(name):
                    return object()
                """
            ),
            convention_name="annotation-coverage",
            severity="warning",
        )

        assert len(result) == 2
        assert result[0].convention_name == "annotation-coverage"
        assert result[0].severity == "warning"
        assert result[0].file_path == "src/service.py"

    def test_missing_annotation_diagnostics_include_expected_and_fix_hint(self) -> None:
        result = check_annotate_functions(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self, value):
                        return value
                """
            ),
        )

        param_diag, return_diag = result

        assert param_diag.expected is not None
        assert "value" in param_diag.expected
        assert param_diag.fix_hint is not None
        assert "Service.run" in param_diag.fix_hint

        assert return_diag.expected == "return type annotation"
        assert return_diag.fix_hint is not None
        assert "Service.run" in return_diag.fix_hint
