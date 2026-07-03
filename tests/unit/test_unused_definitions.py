from __future__ import annotations

import ast
import textwrap

from konpy.unused.definitions import Definition, collect_definitions


def collect(source: str) -> list[Definition]:
    module = ast.parse(textwrap.dedent(source).strip() + "\n")
    return collect_definitions(module=module, module_path="src/mod.py")


def by_qualname(definitions: list[Definition]) -> dict[str, Definition]:
    return {definition.qualname: definition for definition in definitions}


class TestModuleLevel:
    def test_collects_functions_and_async_functions(self) -> None:
        definitions = by_qualname(
            collect(
                """
                def sync_fn():
                    pass

                async def async_fn():
                    pass
                """
            )
        )

        assert definitions["sync_fn"].kind == "function"
        assert definitions["async_fn"].kind == "function"

    def test_collects_classes(self) -> None:
        definitions = by_qualname(collect("class Thing:\n    pass"))

        assert definitions["Thing"].kind == "class"

    def test_collects_constants_from_assign_and_ann_assign(self) -> None:
        definitions = by_qualname(
            collect(
                """
                NAME = "value"
                count: int = 3
                lower = 1
                """
            )
        )

        assert definitions["NAME"].kind == "constant"
        assert definitions["count"].kind == "constant"
        # non-uppercase names are still collected; classification decides fate
        assert definitions["lower"].kind == "constant"

    def test_ignores_tuple_unpacking_targets(self) -> None:
        definitions = by_qualname(collect("a, b = 1, 2"))

        assert definitions == {}

    def test_records_position(self) -> None:
        definitions = by_qualname(collect("X = 1\ndef fn():\n    pass"))

        assert definitions["fn"].lineno == 2
        assert definitions["fn"].col == 1


class TestClassBody:
    def test_collects_methods_with_qualnames(self) -> None:
        definitions = by_qualname(
            collect(
                """
                class Svc:
                    def method(self):
                        pass

                    async def amethod(self):
                        pass
                """
            )
        )

        assert definitions["Svc.method"].kind == "method"
        assert definitions["Svc.amethod"].kind == "method"

    def test_collects_class_attributes(self) -> None:
        definitions = by_qualname(
            collect(
                """
                class Model:
                    name: str
                    count = 0
                """
            )
        )

        assert definitions["Model.name"].kind == "attribute"
        assert definitions["Model.count"].kind == "attribute"

    def test_records_owning_class_bases_and_decorators(self) -> None:
        definitions = by_qualname(
            collect(
                """
                @dataclass
                class Model(BaseModel, Generic[T]):
                    name: str
                """
            )
        )

        attribute = definitions["Model.name"]
        assert attribute.class_bases == ("BaseModel", "Generic")
        assert attribute.class_decorators == ("dataclass",)

    def test_does_not_recurse_into_nested_functions(self) -> None:
        definitions = by_qualname(
            collect(
                """
                def outer():
                    def inner():
                        pass
                    return inner
                """
            )
        )

        assert "outer" in definitions
        assert "outer.inner" not in definitions
        assert "inner" not in definitions


class TestDecorators:
    def test_strips_call_parens_from_decorator_names(self) -> None:
        definitions = by_qualname(
            collect(
                """
                @app.get("/x")
                @field_validator("name")
                def fn():
                    pass
                """
            )
        )

        assert definitions["fn"].decorators == ("app.get", "field_validator")

    def test_plain_attribute_decorator(self) -> None:
        definitions = by_qualname(
            collect(
                """
                @pytest.fixture
                def fixture_fn():
                    pass
                """
            )
        )

        assert definitions["fixture_fn"].decorators == ("pytest.fixture",)
