from __future__ import annotations

import textwrap

from konsistent.core.context import PredicateContext
from konsistent.core.filesystem import FakeFileSystem
from konsistent.core.placeholders import PlaceholderValue
from konsistent.predicates.import_ import check_import
from konsistent.predicates.import_types import check_import_types
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


class TestImport:
    def test_returns_no_diagnostics_when_import_is_found(self) -> None:
        result = check_import(
            expected=["useState"],
            context=context(),
            structure=parse_source("from react import useState"),
        )

        assert result == []

    def test_returns_diagnostic_when_import_is_missing(self) -> None:
        result = check_import(
            expected=["useState"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import "useState"'
        assert result[0].predicate_name == "import"
        assert result[0].file_path == "src/index.py"

    def test_ignores_type_imports(self) -> None:
        result = check_import(
            expected=["MyType"],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .types import MyType
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import "MyType"'

    def test_returns_diagnostic_when_from_does_not_match(self) -> None:
        result = check_import(
            expected=[{"name": "useState", "from": "react"}],
            context=context(),
            structure=parse_source("from preact import useState"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import "useState"'

    def test_checks_from_constraint_when_specified(self) -> None:
        result = check_import(
            expected=[{"name": "helper", "from": ".base"}],
            context=context(),
            structure=parse_source("from .base import helper"),
        )

        assert result == []

    def test_requires_as_written_dotted_relative_from_constraint(self) -> None:
        result = check_import(
            expected=[{"name": "helper", "from": "base"}],
            context=context(),
            structure=parse_source("from .base import helper"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import "helper"'

    def test_resolves_template_placeholders_in_name(self) -> None:
        result = check_import(
            expected=["use${name}"],
            context=context({"name": PlaceholderValue("State")}),
            structure=parse_source("from react import useState"),
        )

        assert result == []

    def test_resolves_template_placeholders_in_from(self) -> None:
        result = check_import(
            expected=[{"name": "helper", "from": ".${name}"}],
            context=context({"name": PlaceholderValue("base")}),
            structure=parse_source("from .base import helper"),
        )

        assert result == []

    def test_accepts_string_shorthand_without_from_constraint(self) -> None:
        result = check_import(
            expected=["useState"],
            context=context(),
            structure=parse_source("from any_package import useState"),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_import(
            expected=["Missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="regular-imports",
        )

        assert result[0].convention_name == "regular-imports"


class TestImportTypes:
    def test_returns_no_diagnostics_when_type_import_is_found(self) -> None:
        result = check_import_types(
            expected=["MyType"],
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

    def test_returns_diagnostic_when_type_import_is_missing(self) -> None:
        result = check_import_types(
            expected=["MyType"],
            context=context(),
            structure=parse_source(""),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import type "MyType"'
        assert result[0].predicate_name == "importTypes"
        assert result[0].file_path == "src/index.py"

    def test_ignores_non_type_imports(self) -> None:
        result = check_import_types(
            expected=["MyType"],
            context=context(),
            structure=parse_source("from .types import MyType"),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import type "MyType"'

    def test_checks_from_constraint_when_specified(self) -> None:
        result = check_import_types(
            expected=[{"name": "MyType", "from": ".base"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .base import MyType
                """
            ),
        )

        assert result == []

    def test_returns_diagnostic_when_from_does_not_match(self) -> None:
        result = check_import_types(
            expected=[{"name": "MyType", "from": ".correct_module"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .wrong_module import MyType
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import type "MyType"'

    def test_requires_as_written_dotted_relative_type_import_from(self) -> None:
        result = check_import_types(
            expected=[{"name": "MyType", "from": "base"}],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .base import MyType
                """
            ),
        )

        assert len(result) == 1
        assert result[0].message == 'Missing import type "MyType"'

    def test_resolves_template_placeholders_in_name(self) -> None:
        result = check_import_types(
            expected=["${name}Props"],
            context=context({"name": PlaceholderValue("Button")}),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .types import ButtonProps
                """
            ),
        )

        assert result == []

    def test_resolves_template_placeholders_in_from(self) -> None:
        result = check_import_types(
            expected=[{"name": "Config", "from": ".${name}"}],
            context=context({"name": PlaceholderValue("config")}),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .config import Config
                """
            ),
        )

        assert result == []

    def test_accepts_string_shorthand_without_from_constraint(self) -> None:
        result = check_import_types(
            expected=["MyType"],
            context=context(),
            structure=parse_source(
                """
                from typing import TYPE_CHECKING

                if TYPE_CHECKING:
                    from .any_module import MyType
                """
            ),
        )

        assert result == []

    def test_includes_convention_name_when_provided(self) -> None:
        result = check_import_types(
            expected=["Missing"],
            context=context(),
            structure=parse_source(""),
            convention_name="type-imports",
        )

        assert result[0].convention_name == "type-imports"
