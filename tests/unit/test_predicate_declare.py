from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.core.placeholders import PlaceholderValue
from konpy.predicates.declare_classes import check_declare_classes
from konpy.predicates.declare_constants import check_declare_constants
from konpy.predicates.declare_functions import check_declare_functions
from konpy.predicates.declare_interfaces import check_declare_interfaces
from konpy.predicates.declare_types import check_declare_types
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


class TestDeclareTypes:
    def test_passes_for_local_type_and_protocol_declarations(self) -> None:
        structure = parse_source(
            """
            from typing import Protocol, TypeAlias

            __all__ = []

            class Thing(Protocol):
                pass

            ThingInput: TypeAlias = str
            """
        )

        result = check_declare_types(
            expected=["Thing", "ThingInput"],
            context=context(),
            structure=structure,
        )

        assert result == []

    def test_rejects_exported_local_type_declarations(self) -> None:
        structure = parse_source(
            """
            from typing import TypeAlias

            ThingInput: TypeAlias = str
            """
        )

        result = check_declare_types(
            expected=["ThingInput"],
            context=context(),
            structure=structure,
        )

        assert len(result) == 1
        assert result[0].message == 'Local type declaration "ThingInput" must not be exported'
        assert result[0].predicate_name == "declareTypes"

    def test_reports_missing_type_declarations(self) -> None:
        result = check_declare_types(
            expected=["ThingInput"],
            context=context(),
            structure=parse_source("__all__ = []"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing local type declaration "ThingInput"'


class TestDeclareConstants:
    def test_passes_for_local_constant_declarations(self) -> None:
        structure = parse_source(
            """
            from typing import Final

            __all__ = []

            thingId: Final[str] = "thing"
            """
        )

        result = check_declare_constants(
            expected=["thingId"],
            context=context(),
            structure=structure,
        )

        assert result == []

    def test_rejects_exported_local_constants(self) -> None:
        structure = parse_source(
            """
            from typing import Final

            thingId: Final[str] = "thing"
            """
        )

        result = check_declare_constants(
            expected=["thingId"],
            context=context(),
            structure=structure,
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Local constant declaration "thingId" must not be exported'
        )
        assert result[0].predicate_name == "declareConstants"

    def test_reports_missing_constant_declarations(self) -> None:
        result = check_declare_constants(
            expected=["thingId"],
            context=context(),
            structure=parse_source("__all__ = []"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing local constant declaration "thingId"'


class TestDeclareFunctions:
    def test_passes_for_local_function_declarations(self) -> None:
        structure = parse_source(
            """
            __all__ = []

            def createThing():
                pass
            """
        )

        result = check_declare_functions(
            expected=["createThing"],
            context=context(),
            structure=structure,
        )

        assert result == []

    def test_rejects_exported_local_functions(self) -> None:
        structure = parse_source(
            """
            def createThing():
                pass
            """
        )

        result = check_declare_functions(
            expected=["createThing"],
            context=context(),
            structure=structure,
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Local function declaration "createThing" must not be exported'
        )

    def test_checks_local_function_signatures(self) -> None:
        structure = parse_source(
            """
            __all__ = []

            def createThing(config: WrongConfig) -> WrongThing:
                pass
            """
        )

        result = check_declare_functions(
            expected=[
                {
                    "name": "createThing",
                    "receiveParamOfType": "ThingConfig",
                    "returnValueOfType": "Thing",
                }
            ],
            context=context(),
            structure=structure,
        )

        assert len(result) == 2
        assert (
            result[0].message
            == 'Function "createThing" must receive a parameter of type "ThingConfig"'
        )
        assert result[1].message == 'Function "createThing" must return value of type "Thing"'

    def test_checks_ordered_local_function_params(self) -> None:
        structure = parse_source(
            """
            __all__ = []

            def createThing(config: ThingConfig, ctx: WrongContext):
                pass
            """
        )

        result = check_declare_functions(
            expected=[
                {
                    "name": "createThing",
                    "receiveParamsOfTypes": ["ThingConfig", "ThingContext"],
                }
            ],
            context=context(),
            structure=structure,
        )

        assert len(result) == 1
        assert (
            result[0].message
            == 'Function "createThing" parameter 2 must be of type "ThingContext"'
        )


class TestDeclareInterfaces:
    def test_passes_for_local_protocol_declarations(self) -> None:
        structure = parse_source(
            """
            from typing import Protocol

            __all__ = []

            class Thing(Protocol):
                pass
            """
        )

        result = check_declare_interfaces(
            expected=["Thing"],
            context=context(),
            structure=structure,
        )

        assert result == []

    def test_checks_local_protocol_extends_clauses(self) -> None:
        structure = parse_source(
            """
            from typing import Protocol

            __all__ = []

            class Thing(OtherThing, Protocol):
                pass
            """
        )

        result = check_declare_interfaces(
            expected=[{"name": "Thing", "extend": "BaseThing"}],
            context=context(),
            structure=structure,
        )

        assert len(result) == 1
        assert result[0].message == 'Interface "Thing" must extend "BaseThing"'

    def test_resolves_declaration_templates(self) -> None:
        structure = parse_source(
            """
            from typing import Protocol

            __all__ = []

            class ThingConfig(Protocol):
                pass
            """
        )

        result = check_declare_interfaces(
            expected=[{"name": "${name}Config"}],
            context=context({"name": PlaceholderValue("Thing")}),
            structure=structure,
        )

        assert result == []


class TestDeclareClasses:
    def test_passes_for_local_class_declarations(self) -> None:
        structure = parse_source(
            """
            __all__ = []

            class Thing:
                pass
            """
        )

        result = check_declare_classes(
            expected=["Thing"],
            context=context(),
            structure=structure,
        )

        assert result == []

    def test_checks_local_class_heritage(self) -> None:
        structure = parse_source(
            """
            __all__ = []

            class Thing(OtherThing):
                pass
            """
        )

        result = check_declare_classes(
            expected=[
                {
                    "name": "Thing",
                    "extend": "BaseThing",
                    "implement": ["Serializable"],
                }
            ],
            context=context(),
            structure=structure,
        )

        assert len(result) == 2
        assert result[0].message == 'Class "Thing" must extend "BaseThing"'
        assert result[1].message == 'Class "Thing" must implement "Serializable"'
