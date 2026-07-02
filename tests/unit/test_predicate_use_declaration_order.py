from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.use_declaration_order import check_use_declaration_order
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


class TestUseDeclarationOrder:
    def test_passes_when_present_declaration_symbols_follow_configured_order(self) -> None:
        result = check_use_declaration_order(
            expected=["ALPHA", "BETA", "GAMMA"],
            context=context(),
            structure=parse_source(
                """
                ALPHA = 1
                GAMMA = 3
                """
            ),
        )

        assert result == []

    def test_does_not_require_missing_symbols(self) -> None:
        result = check_use_declaration_order(
            expected=["ALPHA", "BETA", "GAMMA"],
            context=context(),
            structure=parse_source("BETA = 2"),
        )

        assert result == []

    def test_reports_declarations_after_a_later_configured_symbol(self) -> None:
        result = check_use_declaration_order(
            expected=["ALPHA", "BETA", "GAMMA"],
            context=context(),
            structure=parse_source(
                """
                BETA = 2
                ALPHA = 1
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Symbol "ALPHA" must be declared before "BETA"'
        assert result[0].predicate_name == "useDeclarationOrder"
        assert result[0].line == 2

    def test_considers_named_re_exports_when_no_local_declaration_exists(self) -> None:
        result = check_use_declaration_order(
            expected=["Alpha", "Beta", "Gamma"],
            context=context(),
            structure=parse_source(
                """
                from .beta import Beta
                from .alpha import Alpha
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Symbol "Alpha" must be declared before "Beta"'

    def test_uses_local_declaration_position_before_matching_named_export(self) -> None:
        result = check_use_declaration_order(
            expected=["ALPHA", "BETA"],
            context=context(),
            structure=parse_source(
                """
                ALPHA = 1
                from .beta import BETA
                from .alpha import ALPHA
                """
            ),
        )

        assert result == []

    def test_ignores_missing_symbols(self) -> None:
        result = check_use_declaration_order(
            expected=["ALPHA", "BETA"],
            context=context(),
            structure=parse_source(
                """
                BETA = 2
                """
            ),
        )

        assert result == []

    def test_resolves_templates_in_configured_symbols(self) -> None:
        result = check_use_declaration_order(
            expected=["${prefix}Alpha", "${prefix}Beta"],
            context=context({"prefix": PlaceholderValue("Thing")}),
            structure=parse_source(
                """
                ThingAlpha = 1
                ThingBeta = 2
                """
            ),
        )

        assert result == []
