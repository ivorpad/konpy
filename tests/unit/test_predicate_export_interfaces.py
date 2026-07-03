from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.core.placeholders import PlaceholderValue
from konpy.predicates.export_interfaces import check_export_interfaces
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


class TestExportInterfaces:
    def test_returns_no_diagnostics_when_protocol_is_exported(self) -> None:
        result = check_export_interfaces(
            expected=["MyInterface"],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_no_diagnostics_when_extend_is_satisfied(self) -> None:
        result = check_export_interfaces(
            expected=[{"name": "MyInterface", "extend": "BaseInterface"}],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(BaseInterface, Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_with_line_number_when_extend_is_violated(self) -> None:
        result = check_export_interfaces(
            expected=[{"name": "MyInterface", "extend": "BaseInterface"}],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(OtherInterface, Protocol):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Interface "MyInterface" must extend "BaseInterface"'
        assert result[0].predicate_name == "exportInterfaces"
        assert result[0].line == 3
        assert result[0].column == 1

    def test_returns_diagnostic_when_interface_is_missing(self) -> None:
        result = check_export_interfaces(
            expected=["MissingInterface"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export interface "MissingInterface"'
        assert result[0].predicate_name == "exportInterfaces"
        assert result[0].file_path == "src/index.py"
        assert result[0].line is None
        assert result[0].column is None

    def test_resolves_template_placeholders_in_interface_names(self) -> None:
        result = check_export_interfaces(
            expected=["${name}Props"],
            context=context({"name": PlaceholderValue("Button")}),
            structure=parse_source(
                """
                from typing import Protocol

                class ButtonProps(Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_resolves_template_placeholders_in_extend_values(self) -> None:
        result = check_export_interfaces(
            expected=[{"name": "MyInterface", "extend": "${base}Interface"}],
            context=context({"base": PlaceholderValue("Base")}),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(BaseInterface, Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_export_interfaces(
            expected=["Missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="interface-convention",
        )

        assert result[0].convention_name == "interface-convention"

    def test_accepts_string_shorthand_expanding_to_name(self) -> None:
        result = check_export_interfaces(
            expected=["Foo"],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class Foo(Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_allow_omissions_accepts_first_generic_arg_of_pick(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "BaseInterface", "allowOmissions": True},
                }
            ],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Pick[BaseInterface, str], Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_allow_omissions_false_rejects_first_generic_arg_of_pick(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "BaseInterface"},
                }
            ],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Pick[BaseInterface, str], Protocol):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Interface "MyInterface" must extend "BaseInterface"'

    def test_allow_omissions_accepts_first_generic_arg_of_omit(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "BaseInterface", "allowOmissions": True},
                }
            ],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Omit[BaseInterface, str], Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_allow_omissions_accepts_direct_match(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "BaseInterface", "allowOmissions": True},
                }
            ],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(BaseInterface, Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_allow_omissions_still_rejects_when_target_is_not_referenced(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "BaseInterface", "allowOmissions": True},
                }
            ],
            context=context(),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Pick[OtherInterface, str], Protocol):
                    pass
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Interface "MyInterface" must extend "BaseInterface"'

    def test_resolves_template_placeholders_in_extend_object_type(self) -> None:
        result = check_export_interfaces(
            expected=[
                {
                    "name": "MyInterface",
                    "extend": {"type": "${base}Interface", "allowOmissions": True},
                }
            ],
            context=context({"base": PlaceholderValue("Base")}),
            structure=parse_source(
                """
                from typing import Protocol

                class MyInterface(Partial[BaseInterface], Protocol):
                    pass
                """
            ),
        )

        assert result == []

    def test_type_aliases_do_not_satisfy_interface_requirements(self) -> None:
        result = check_export_interfaces(
            expected=["MyInterface"],
            context=context(),
            structure=parse_source(
                """
                from typing import TypeAlias

                MyInterface: TypeAlias = int
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing export interface "MyInterface"'
