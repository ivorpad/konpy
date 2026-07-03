from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.core.placeholders import PlaceholderValue
from konpy.predicates.export_classes import check_export_classes
from konpy.python_ast.parser import parse_file_structure


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


class TestExportClasses:
    def test_returns_no_diagnostics_when_class_is_exported(self) -> None:
        result = check_export_classes(
            expected=["MyClass"],
            context=context(),
            structure=parse_source("class MyClass: pass"),
        )

        assert result == []

    def test_returns_no_diagnostics_when_extend_is_satisfied(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": "BaseClass"}],
            context=context(),
            structure=parse_source("class MyClass(BaseClass): pass"),
        )

        assert result == []

    def test_returns_diagnostic_with_line_number_when_extend_is_violated(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": "BaseClass"}],
            context=context(),
            structure=parse_source(
                """
                class MyClass(OtherClass):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Class "MyClass" must extend "BaseClass"'
        assert result[0].predicate_name == "exportClasses"
        assert result[0].line == 1
        assert result[0].column == 1

    def test_returns_diagnostic_when_class_is_missing(self) -> None:
        result = check_export_classes(
            expected=["MissingClass"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export class "MissingClass"'
        assert result[0].predicate_name == "exportClasses"
        assert result[0].file_path == "src/index.py"
        assert result[0].line is None
        assert result[0].column is None

    def test_resolves_template_placeholders_in_class_names(self) -> None:
        result = check_export_classes(
            expected=["${name}Controller"],
            context=context({"name": PlaceholderValue("User")}),
            structure=parse_source("class UserController: pass"),
        )

        assert result == []

    def test_resolves_template_placeholders_in_extend_values(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": "${base}Class"}],
            context=context({"base": PlaceholderValue("Base")}),
            structure=parse_source("class MyClass(BaseClass): pass"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export_classes(
            expected=["Missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="class-convention",
        )

        assert result[0].convention_name == "class-convention"

    def test_accepts_string_shorthand_expanding_to_name(self) -> None:
        result = check_export_classes(
            expected=["Foo"],
            context=context(),
            structure=parse_source("class Foo: pass"),
        )

        assert result == []

    def test_accepts_object_form_for_extend_with_type_field(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": {"type": "BaseClass"}}],
            context=context(),
            structure=parse_source("class MyClass(BaseClass): pass"),
        )

        assert result == []

    def test_returns_no_diagnostics_when_implement_is_satisfied(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "implement": ["Serializable"]}],
            context=context(),
            structure=parse_source("class MyClass(BaseClass, Serializable): pass"),
        )

        assert result == []

    def test_returns_no_diagnostics_when_multiple_implements_are_satisfied(self) -> None:
        result = check_export_classes(
            expected=[
                {
                    "name": "MyClass",
                    "implement": ["Serializable", "Disposable"],
                }
            ],
            context=context(),
            structure=parse_source(
                "class MyClass(BaseClass, Serializable, Disposable): pass"
            ),
        )

        assert result == []

    def test_returns_diagnostic_when_implement_is_violated(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "implement": ["Serializable"]}],
            context=context(),
            structure=parse_source("class MyClass(BaseClass): pass"),
        )

        assert len(result) == 1
        assert result[0].message == 'Class "MyClass" must implement "Serializable"'
        assert result[0].line == 1

    def test_returns_diagnostics_for_each_missing_implement(self) -> None:
        result = check_export_classes(
            expected=[
                {
                    "name": "MyClass",
                    "implement": ["Serializable", "Disposable"],
                }
            ],
            context=context(),
            structure=parse_source("class MyClass(BaseClass, Serializable): pass"),
        )

        assert len(result) == 1
        assert result[0].message == 'Class "MyClass" must implement "Disposable"'

    def test_resolves_template_placeholders_in_implement_values(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "implement": ["${name}Handler"]}],
            context=context({"name": PlaceholderValue("Event")}),
            structure=parse_source("class MyClass(BaseClass, EventHandler): pass"),
        )

        assert result == []

    def test_accepts_object_form_for_implement_with_type_field(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "implement": [{"type": "Serializable"}]}],
            context=context(),
            structure=parse_source("class MyClass(BaseClass, Serializable): pass"),
        )

        assert result == []

    def test_missing_export_diagnostic_includes_expected_and_fix_hint(self) -> None:
        result = check_export_classes(
            expected=["MissingClass"],
            context=context(),
            structure=parse_source(""),
        )

        assert result[0].expected == "MissingClass"
        assert result[0].fix_hint is not None
        assert "MissingClass" in result[0].fix_hint

    def test_extend_violation_includes_expected_and_found(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": "BaseClass"}],
            context=context(),
            structure=parse_source(
                """
                class MyClass(OtherClass):
                    pass
                """
            ),
        )

        assert result[0].expected == "BaseClass"
        assert result[0].found == "OtherClass"

    def test_extend_violation_found_is_none_when_no_base_class(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "extend": "BaseClass"}],
            context=context(),
            structure=parse_source("class MyClass: pass"),
        )

        assert result[0].found is None

    def test_implement_violation_includes_expected_and_found(self) -> None:
        result = check_export_classes(
            expected=[
                {
                    "name": "MyClass",
                    "implement": ["Serializable", "Disposable"],
                }
            ],
            context=context(),
            structure=parse_source("class MyClass(BaseClass, Serializable): pass"),
        )

        assert result[0].expected == "Disposable"
        assert result[0].found == "Serializable"

    def test_implement_violation_found_is_none_when_no_bases_implemented(self) -> None:
        result = check_export_classes(
            expected=[{"name": "MyClass", "implement": ["Serializable"]}],
            context=context(),
            structure=parse_source("class MyClass: pass"),
        )

        assert result[0].found is None
