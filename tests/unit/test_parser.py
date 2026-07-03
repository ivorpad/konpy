from __future__ import annotations

import textwrap

from konpy.python_ast.parser import parse_file_structure
from konpy.python_ast.structure import SourcePosition


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "module.py")


def names(entries):
    return [entry.name for entry in entries]


class TestAllHandling:
    def test_literal_list_controls_public_exports(self) -> None:
        result = parse_source(
            """
            __all__ = ["Public"]
            def Public(): ...
            def Hidden(): ...
            """
        )

        assert result.all_names == ("Public",)
        assert result.all_is_dynamic is False
        assert names(result.exports) == ["Public"]

    def test_literal_tuple_augmented_extend_and_append(self) -> None:
        result = parse_source(
            """
            __all__ = ("A",)
            __all__ += ["B"]
            __all__.extend(("C",))
            __all__.append("D")
            def A(): ...
            def B(): ...
            def C(): ...
            def D(): ...
            def E(): ...
            """
        )

        assert result.all_names == ("A", "B", "C", "D")
        assert names(result.exports) == ["A", "B", "C", "D"]

    def test_annotated_all_assignment(self) -> None:
        result = parse_source(
            """
            __all__: list[str] = ["VALUE"]
            VALUE = 1
            OTHER = 2
            """
        )

        assert result.all_names == ("VALUE",)
        assert names(result.constants) == ["VALUE", "OTHER"]
        assert names(result.exports) == ["VALUE"]

    def test_dynamic_all_falls_back_to_underscore_publicness(self) -> None:
        result = parse_source(
            """
            __all__ = get_names()
            def public(): ...
            def _private(): ...
            """
        )

        assert result.all_names is None
        assert result.all_is_dynamic is True
        assert names(result.exports) == ["public"]

    def test_non_literal_mutation_marks_all_dynamic(self) -> None:
        result = parse_source(
            """
            __all__ = ["A"]
            __all__.append(name)
            def A(): ...
            def B(): ...
            """
        )

        assert result.all_names is None
        assert result.all_is_dynamic is True
        assert names(result.exports) == ["A", "B"]


class TestImports:
    def test_import_forms_and_sources(self) -> None:
        result = parse_source(
            """
            import a.b.c
            import d.e as alias
            from pkg import x, y as z
            from . import local
            from .sub import item as sub_item
            from ..parent import item
            from star import *
            """
        )

        assert [(entry.name, entry.from_, entry.is_type) for entry in result.imports] == [
            ("a", "a.b.c", False),
            ("alias", "d.e", False),
            ("x", "pkg", False),
            ("z", "pkg", False),
            ("local", ".", False),
            ("sub_item", ".sub", False),
            ("item", "..parent", False),
            ("*", "star", False),
        ]
        assert [(entry.from_, entry.level) for entry in result.import_sources] == [
            ("a.b.c", 0),
            ("d.e", 0),
            ("pkg", 0),
            (".", 1),
            (".sub", 1),
            ("..parent", 2),
            ("star", 0),
        ]

    def test_from_import_source_is_once_per_statement(self) -> None:
        result = parse_source("from module import a, b, c")

        assert len(result.imports) == 3
        assert len(result.import_sources) == 1
        assert result.import_sources[0].from_ == "module"

    def test_public_imports_create_re_exports_without_source_name_on_import_info(self) -> None:
        result = parse_source(
            """
            from module import source as exported
            import package.sub as pkg
            """
        )

        assert [(entry.name, entry.from_, entry.kind) for entry in result.exports] == [
            ("exported", "module", "re-export"),
            ("pkg", "package.sub", "re-export"),
        ]
        assert [
            (entry.name, entry.source_name, entry.from_)
            for entry in result.named_export_symbols
        ] == [
            ("exported", "source", "module"),
            ("pkg", "package", "package.sub"),
        ]
        assert not hasattr(result.imports[0], "source_name")

    def test_all_controls_import_re_exports(self) -> None:
        result = parse_source(
            """
            __all__ = ["exported"]
            from module import exported, hidden
            """
        )

        assert names(result.exports) == ["exported"]


class TestTypeCheckingImports:
    def test_bare_type_checking_alias_marks_body_imports_as_type(self) -> None:
        result = parse_source(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                from .types_mod import TypeA
                import pkg.types as types_pkg
                VALUE = 1
            """
        )

        assert ("TypeA", ".types_mod", True) in [
            (entry.name, entry.from_, entry.is_type) for entry in result.imports
        ]
        assert ("types_pkg", "pkg.types", True) in [
            (entry.name, entry.from_, entry.is_type) for entry in result.imports
        ]
        assert names(result.constants) == []

    def test_type_checking_alias_and_runtime_else_imports(self) -> None:
        result = parse_source(
            """
            from typing import TYPE_CHECKING as TC

            if TC:
                from only_types import T
            else:
                from runtime import value
            """
        )

        assert [(entry.name, entry.is_type) for entry in result.imports] == [
            ("TC", False),
            ("T", True),
            ("value", False),
        ]

    def test_typing_module_alias_attribute_test(self) -> None:
        result = parse_source(
            """
            import typing as t

            if t.TYPE_CHECKING:
                from model import Model
            """
        )

        assert ("Model", True) in [(entry.name, entry.is_type) for entry in result.imports]

    def test_typing_attribute_test(self) -> None:
        result = parse_source(
            """
            import typing

            if typing.TYPE_CHECKING:
                from model import Model
            """
        )

        assert ("Model", True) in [(entry.name, entry.is_type) for entry in result.imports]


class TestFunctions:
    def test_regular_async_params_and_return_types(self) -> None:
        result = parse_source(
            """
            def sync(
                a: list[int],
                b,
                /,
                c: dict[str, int],
                *args,
                d: str,
            ) -> tuple[str, int]:
                pass

            async def async_fn(x: int) -> None:
                pass
            """
        )

        assert names(result.functions) == ["sync", "async_fn"]
        sync = result.functions[0]
        assert [
            (param.name, param.type_name.text if param.type_name else None)
            for param in sync.params
        ] == [
            ("a", "list[int]"),
            ("b", None),
            ("c", "dict[str, int]"),
        ]
        assert sync.params[0].type_name.base_name == "list"
        assert sync.return_type is not None
        assert sync.return_type.text == "tuple[str, int]"
        assert sync.return_type.base_name == "tuple"
        assert result.functions[1].return_type.text == "None"


class TestDocstringTargets:
    def test_collects_module_class_function_and_method_docstring_targets(self) -> None:
        result = parse_source(
            '''
            """Module docs."""

            class Service:
                """Service docs."""

                def run(self):
                    """Run docs."""
                    return None

                def missing_method(self):
                    return None

            def make_service():
                """Factory docs."""
                return Service()

            def missing_function():
                return None
            '''
        )

        assert [
            (
                entry.kind,
                entry.name,
                entry.qualified_name,
                entry.has_docstring,
                entry.is_public,
            )
            for entry in result.docstring_targets
        ] == [
            ("module", "<module>", "<module>", True, True),
            ("class", "Service", "Service", True, True),
            ("function", "run", "Service.run", True, True),
            ("function", "missing_method", "Service.missing_method", False, True),
            ("function", "make_service", "make_service", True, True),
            ("function", "missing_function", "missing_function", False, True),
        ]

    def test_docstring_target_publicness_reuses_export_publicness(self) -> None:
        result = parse_source(
            """
            __all__ = ["PublicClass", "public_func"]

            class PublicClass:
                def method(self):
                    pass

                def _hidden(self):
                    pass

            class HiddenClass:
                def method(self):
                    pass

            def public_func():
                pass

            def hidden_func():
                pass
            """
        )

        assert {
            entry.qualified_name: entry.is_public
            for entry in result.docstring_targets
        } == {
            "<module>": True,
            "PublicClass": True,
            "PublicClass.method": True,
            "PublicClass._hidden": False,
            "HiddenClass": False,
            "HiddenClass.method": False,
            "public_func": True,
            "hidden_func": False,
        }

    def test_docstring_target_positions_use_definition_positions(self) -> None:
        result = parse_source(
            '''
            """Module docs."""

            class Service:
                def run(self):
                    pass
            '''
        )

        positions = {
            entry.qualified_name: entry.pos for entry in result.docstring_targets
        }
        assert positions["<module>"] == SourcePosition(line=1, column=1)
        assert positions["Service"] == SourcePosition(line=3, column=1)
        assert positions["Service.run"] == SourcePosition(line=4, column=5)


class TestFunctionAnnotationTargets:
    def test_collects_top_level_functions_and_direct_methods_for_annotation_coverage(
        self,
    ) -> None:
        result = parse_source(
            """
            class Service:
                def run(
                    self,
                    value: str,
                    *items: int,
                    flag: bool,
                    retry,
                    **kwargs: str,
                ) -> None:
                    pass

                @classmethod
                def build(cls, name: str) -> Service:
                    return cls()

            async def fetch(item_id: int, *, timeout: float, retry) -> str:
                return ""
            """
        )

        assert names(result.functions) == ["fetch"]
        targets = {
            entry.qualified_name: entry
            for entry in result.function_annotation_targets
        }

        run = targets["Service.run"]
        assert [
            (param.name, param.type_name.text if param.type_name else None)
            for param in run.params
        ] == [
            ("value", "str"),
            ("items", "int"),
            ("flag", "bool"),
            ("retry", None),
            ("kwargs", "str"),
        ]
        assert run.return_type is not None
        assert run.return_type.text == "None"

        build = targets["Service.build"]
        assert [
            (param.name, param.type_name.text if param.type_name else None)
            for param in build.params
        ] == [("name", "str")]
        assert build.return_type is not None
        assert build.return_type.text == "Service"

        fetch = targets["fetch"]
        assert [
            (param.name, param.type_name.text if param.type_name else None)
            for param in fetch.params
        ] == [
            ("item_id", "int"),
            ("timeout", "float"),
            ("retry", None),
        ]
        assert fetch.return_type is not None
        assert fetch.return_type.text == "str"

    def test_annotation_target_publicness_matches_docstring_target_publicness(self) -> None:
        result = parse_source(
            """
            __all__ = ["PublicClass", "public_func"]

            class PublicClass:
                def method(self):
                    pass

                def _hidden(self):
                    pass

            class HiddenClass:
                def method(self):
                    pass

            def public_func():
                pass

            def hidden_func():
                pass
            """
        )

        assert {
            entry.qualified_name: entry.is_public
            for entry in result.function_annotation_targets
        } == {
            "PublicClass.method": True,
            "PublicClass._hidden": False,
            "HiddenClass.method": False,
            "public_func": True,
            "hidden_func": False,
        }


class TestClassesAndProtocols:
    def test_simple_class_and_multiple_bases_split(self) -> None:
        result = parse_source(
            """
            class Child(Base, Mixin, Other):
                pass
            """
        )

        assert result.classes[0].name == "Child"
        assert result.classes[0].extends == "Base"
        assert result.classes[0].implements == ("Mixin", "Other")
        assert result.interfaces == ()
        assert result.declaration_symbols[0].kind == "class"

    def test_protocol_generic_base_creates_interface(self) -> None:
        result = parse_source(
            """
            from typing import Protocol, TypeVar

            T = TypeVar("T")

            class Service(BaseService[T], Protocol[T]):
                pass
            """
        )

        assert result.classes[0].extends == "BaseService"
        assert result.interfaces[0].name == "Service"
        assert result.interfaces[0].extends[0].name == "BaseService"
        assert result.interfaces[0].extends[0].type_arguments == ("T",)
        assert result.declaration_symbols[-1].kind == "protocol"
        assert result.exports[-1].kind == "protocol"
        assert result.exports[-1].is_type is True

    def test_typing_protocol_abc_and_metaclass_abcmeta(self) -> None:
        result = parse_source(
            """
            import typing
            import abc
            from abc import ABCMeta

            class P(typing.Protocol):
                pass

            class A(abc.ABC):
                pass

            class M(metaclass=ABCMeta):
                pass
            """
        )

        assert [entry.name for entry in result.interfaces] == ["P", "A", "M"]
        assert [entry.kind for entry in result.declaration_symbols[-3:]] == [
            "protocol",
            "protocol",
            "protocol",
        ]


class TestAssignmentsConstantsAndTypeAliases:
    def test_uppercase_and_final_constants(self) -> None:
        result = parse_source(
            """
            from typing import Final
            import typing

            VALUE = 1
            lower: Final[int] = 2
            other: typing.Final = 3
            ignored = 4
            """
        )

        assert names(result.constants) == ["VALUE", "lower", "other"]
        assert result.constants[1].type_name.text == "Final[int]"
        assert result.constants[1].type_name.base_name == "Final"

    def test_assignment_re_export_uses_private_import_binding(self) -> None:
        result = parse_source(
            """
            from .module import Original
            Alias = Original
            """
        )

        assert ("Alias", ".module", "re-export") in [
            (entry.name, entry.from_, entry.kind) for entry in result.exports
        ]
        assert ("Alias", "Original", ".module") in [
            (entry.name, entry.source_name, entry.from_) for entry in result.named_export_symbols
        ]
        assert "Alias" not in names(result.constants)

    def test_type_alias_annassign_and_pep695(self) -> None:
        result = parse_source(
            """
            from typing import TypeAlias
            import typing

            Alias: TypeAlias = str
            Other: typing.TypeAlias = int
            type NewAlias = list[str]
            """
        )

        assert names(result.type_aliases) == ["Alias", "Other", "NewAlias"]
        assert [entry.kind for entry in result.declaration_symbols[-3:]] == [
            "type",
            "type",
            "type",
        ]
        assert [entry.kind for entry in result.exports[-3:]] == ["type", "type", "type"]

    def test_type_alias_takes_precedence_over_final_constant(self) -> None:
        result = parse_source(
            """
            from typing import TypeAlias

            VALUE: TypeAlias = str
            """
        )

        assert names(result.type_aliases) == ["VALUE"]
        assert result.constants == ()


class TestBarrelClassification:
    def test_allowed_barrel_statements(self) -> None:
        result = parse_source(
            '''
            """module docs"""
            from typing import TYPE_CHECKING
            from .module import Imported
            __all__ = ["Alias"]
            Alias = Imported

            if TYPE_CHECKING:
                from .types_mod import T
                value = 1
            '''
        )

        assert result.non_barrel_statements == ()

    def test_declarations_and_expressions_are_classified(self) -> None:
        result = parse_source(
            """
            def fn(): ...
            class C: ...
            type Alias = str
            VALUE = 1
            __all__ += dynamic
            call()
            if condition:
                pass
            """
        )

        assert [entry.kind for entry in result.non_barrel_statements] == [
            "declaration",
            "declaration",
            "declaration",
            "declaration",
            "expression",
            "expression",
            "expression",
        ]


class TestPositions:
    def test_positions_are_one_based(self) -> None:
        result = parse_file_structure(
            "\nfrom .module import Imported\n\nVALUE = Imported\n\ndef fn():\n    pass\n",
            "module.py",
        )

        assert result.imports[0].pos == SourcePosition(line=2, column=1)
        assert result.imports[0].from_ == ".module"
        assert result.named_export_symbols[-1].pos == SourcePosition(line=4, column=1)
        assert result.functions[0].pos == SourcePosition(line=6, column=1)

    def test_assignment_target_position_is_used(self) -> None:
        result = parse_file_structure("VALUE = 1\n", "module.py")

        assert result.constants[0].pos == SourcePosition(line=1, column=1)
        assert result.declaration_symbols[0].pos == SourcePosition(line=1, column=1)

    def test_import_source_position_uses_statement_position(self) -> None:
        result = parse_file_structure("from ..pkg import a, b\n", "module.py")

        assert result.import_sources[0].pos == SourcePosition(line=1, column=1)
        assert result.import_sources[0].from_ == "..pkg"
        assert result.imports[1].pos == SourcePosition(line=1, column=1)


class TestSyntaxErrors:
    def test_syntax_error_returns_empty_structure(self) -> None:
        result = parse_file_structure("def broken(:\n", "broken.py")

        assert result.classes == ()
        assert result.constants == ()
        assert result.declaration_symbols == ()
        assert result.default_export_symbols == ()
        assert result.docstring_targets == ()
        assert result.exports == ()
        assert result.function_annotation_targets == ()
        assert result.functions == ()
        assert result.import_sources == ()
        assert result.imports == ()
        assert result.interfaces == ()
        assert result.named_export_symbols == ()
        assert result.non_barrel_statements == ()
        assert result.type_aliases == ()
        assert result.all_names is None
        assert result.all_is_dynamic is False
