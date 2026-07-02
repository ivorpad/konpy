from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.predicates.have_docstrings import check_have_docstrings
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


class TestHaveDocstrings:
    def test_returns_no_diagnostics_when_selected_targets_have_docstrings(self) -> None:
        result = check_have_docstrings(
            expected=True,
            context=context(),
            structure=parse_source(
                '''
                """Module docs."""

                class Service:
                    """Service docs."""

                    def run(self) -> None:
                        """Run docs."""
                        return None

                def create_service() -> Service:
                    """Create docs."""
                    return Service()
                '''
            ),
        )

        assert result == []

    def test_reports_missing_module_class_function_and_method_docstrings(self) -> None:
        result = check_have_docstrings(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self) -> None:
                        return None

                def create_service() -> Service:
                    return Service()
                """
            ),
        )

        assert [(item.message, item.line, item.column) for item in result] == [
            ("Missing module docstring", 1, 1),
            ('Class "Service" must have a docstring', 1, 1),
            ('Function "Service.run" must have a docstring', 2, 5),
            ('Function "create_service" must have a docstring', 5, 1),
        ]
        assert all(item.predicate_name == "haveDocstrings" for item in result)

    def test_module_class_and_function_options_filter_targets(self) -> None:
        result = check_have_docstrings(
            expected={"modules": False, "classes": False, "functions": True},
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self) -> None:
                        return None

                def create_service() -> Service:
                    return Service()
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "Service.run" must have a docstring',
            'Function "create_service" must have a docstring',
        ]

    def test_public_only_skips_private_classes_functions_and_methods(self) -> None:
        result = check_have_docstrings(
            expected={"modules": False, "publicOnly": True},
            context=context(),
            structure=parse_source(
                """
                class Public:
                    def run(self) -> None:
                        return None

                    def _helper(self) -> None:
                        return None

                class _Private:
                    def run(self) -> None:
                        return None

                def public_func() -> None:
                    return None

                def _private_func() -> None:
                    return None
                """
            ),
        )

        assert [item.message for item in result] == [
            'Class "Public" must have a docstring',
            'Function "Public.run" must have a docstring',
            'Function "public_func" must have a docstring',
        ]

    def test_public_only_false_includes_private_targets(self) -> None:
        result = check_have_docstrings(
            expected={
                "modules": False,
                "classes": False,
                "functions": True,
                "publicOnly": False,
            },
            context=context(),
            structure=parse_source(
                """
                class Public:
                    def _helper(self) -> None:
                        return None

                def _private_func() -> None:
                    return None
                """
            ),
        )

        assert [item.message for item in result] == [
            'Function "Public._helper" must have a docstring',
            'Function "_private_func" must have a docstring',
        ]

    def test_literal_all_controls_public_docstring_targets(self) -> None:
        result = check_have_docstrings(
            expected={"modules": False, "publicOnly": True},
            context=context(),
            structure=parse_source(
                """
                __all__ = ["Exported"]

                class Exported:
                    def run(self) -> None:
                        return None

                class Hidden:
                    def run(self) -> None:
                        return None

                def exported_func() -> None:
                    return None
                """
            ),
        )

        assert [item.message for item in result] == [
            'Class "Exported" must have a docstring',
            'Function "Exported.run" must have a docstring',
        ]

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        result = check_have_docstrings(
            expected={"modules": True, "classes": False, "functions": False},
            context=context(),
            structure=parse_source("VALUE = 1"),
            convention_name="docstring-coverage",
            severity="warning",
        )

        assert len(result) == 1
        assert result[0].convention_name == "docstring-coverage"
        assert result[0].severity == "warning"
        assert result[0].file_path == "src/service.py"

    def test_missing_docstring_diagnostics_include_expected_and_fix_hint(self) -> None:
        result = check_have_docstrings(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                class Service:
                    def run(self) -> None:
                        return None

                def create_service() -> Service:
                    return Service()
                """
            ),
        )

        module_diag, class_diag, method_diag, function_diag = result

        assert module_diag.expected is not None
        assert "module docstring" in module_diag.expected
        assert module_diag.fix_hint is not None

        assert class_diag.expected is not None
        assert "Service" in class_diag.expected
        assert class_diag.fix_hint is not None
        assert "Service" in class_diag.fix_hint

        assert method_diag.expected is not None
        assert "Service.run" in method_diag.expected
        assert method_diag.fix_hint is not None
        assert "Service.run" in method_diag.fix_hint

        assert function_diag.expected is not None
        assert "create_service" in function_diag.expected
        assert function_diag.fix_hint is not None
        assert "create_service" in function_diag.fix_hint
