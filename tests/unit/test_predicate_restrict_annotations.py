from __future__ import annotations

import textwrap

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_annotations import check_restrict_annotations
from konpy.python_ast.parser import parse_file_structure


def parse_source(source: str):
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", "src/service.py")


def context() -> PredicateContext:
    return PredicateContext(
        path="src/service.py",
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


def check(source: str, expected: object = True):
    return check_restrict_annotations(
        expected=expected,
        context=context(),
        structure=parse_source(source),
    )


class TestRestrictAnnotationsDefaults:
    def test_defaults_flag_selected_targets_per_occurrence(self) -> None:
        result = check(
            """
            from typing import Any

            VALUE: dict[str, str | int] = {}

            class Model:
                metadata: dict[str, object]

            def handle(payload: dict[str, Any]) -> dict[str, object]:
                return payload

            def nested(payload: list[dict[str, Any]]) -> None:
                pass
            """
        )

        assert [item.found for item in result] == [
            "dict[str, str | int]",
            "dict[str, object]",
            "dict[str, Any]",
            "dict[str, object]",
            "dict[str, Any]",
        ]
        assert [item.line for item in result] == [3, 6, 8, 8, 11]

    def test_defaults_leave_homogeneous_and_non_string_keyed_maps_alone(self) -> None:
        result = check(
            """
            from typing import Any, Mapping

            def handle(
                a: dict[str, str],
                b: Mapping[str, int],
                c: dict[int, Any],
                d: dict[str, list[str]],
            ) -> None:
                pass
            """
        )

        assert result == []

    def test_defaults_flag_union_optional_any_and_object_values(self) -> None:
        result = check(
            """
            from typing import Any, Optional, Union

            def handle(
                a: dict[str, str | list[str]],
                b: dict[str, Union[str, list[str]]],
                c: dict[str, Optional[str]],
                d: dict[str, Any],
                e: dict[str, object],
            ) -> None:
                pass
            """
        )

        assert [item.found for item in result] == [
            "dict[str, str | list[str]]",
            "dict[str, Union[str, list[str]]]",
            "dict[str, Optional[str]]",
            "dict[str, Any]",
            "dict[str, object]",
        ]


class TestRestrictAnnotationsPatterns:
    def test_explicit_forbid_wildcard_flags_matching_annotation(self) -> None:
        result = check(
            """
            def handle(payload: dict[str, list[str]]) -> None:
                pass
            """,
            expected={"forbid": ["dict[str, *]"], "defaults": False},
        )

        assert len(result) == 1
        assert result[0].found == "dict[str, list[str]]"

    def test_allow_beats_defaults(self) -> None:
        result = check(
            """
            from typing import Any

            def handle(payload: dict[str, Any]) -> None:
                pass
            """,
            expected={"allow": ["dict[str, Any]"]},
        )

        assert result == []

    def test_allow_beats_explicit_forbid(self) -> None:
        result = check(
            """
            def handle(payload: dict[str, list[str]]) -> None:
                pass
            """,
            expected={
                "forbid": ["dict[str, *]"],
                "allow": ["dict[str, list[str]]"],
                "defaults": False,
            },
        )

        assert result == []

    def test_allow_can_match_root_annotation_for_nested_occurrence(self) -> None:
        result = check(
            """
            from typing import Any

            def handle(payload: list[dict[str, Any]]) -> None:
                pass
            """,
            expected={"allow": ["list[dict[str, Any]]"]},
        )

        assert result == []

    def test_defaults_false_uses_only_explicit_forbid(self) -> None:
        result = check(
            """
            from typing import Any

            def handle(
                a: dict[str, Any],
                b: dict[str, object],
            ) -> None:
                pass
            """,
            expected={"forbid": ["dict[str, object]"], "defaults": False},
        )

        assert [item.found for item in result] == ["dict[str, object]"]


class TestRestrictAnnotationsPublicOnly:
    def test_public_only_true_skips_private_targets(self) -> None:
        result = check(
            """
            from typing import Any

            PUBLIC: dict[str, Any] = {}
            _PRIVATE: dict[str, Any] = {}

            class Public:
                payload: dict[str, Any]
                _payload: dict[str, Any]

            class _Private:
                payload: dict[str, Any]

            def public(payload: dict[str, Any]) -> None:
                pass

            def _private(payload: dict[str, Any]) -> None:
                pass
            """
        )

        assert [item.message for item in result] == [
            (
                'Annotation "dict[str, Any]" on module constant "PUBLIC" should use '
                "a named record type"
            ),
            (
                'Annotation "dict[str, Any]" on class attribute "Public.payload" '
                "should use a named record type"
            ),
            (
                'Annotation "dict[str, Any]" on parameter "payload" of function '
                '"public" should use a named record type'
            ),
        ]

    def test_public_only_false_includes_private_targets(self) -> None:
        result = check(
            """
            from typing import Any

            PUBLIC: dict[str, Any] = {}
            _PRIVATE: dict[str, Any] = {}

            class Public:
                payload: dict[str, Any]
                _payload: dict[str, Any]

            class _Private:
                payload: dict[str, Any]

            def public(payload: dict[str, Any]) -> None:
                pass

            def _private(payload: dict[str, Any]) -> None:
                pass
            """,
            expected={"publicOnly": False},
        )

        assert [item.found for item in result] == [
            "dict[str, Any]",
            "dict[str, Any]",
            "dict[str, Any]",
            "dict[str, Any]",
            "dict[str, Any]",
            "dict[str, Any]",
            "dict[str, Any]",
        ]
        assert len(result) == 7


class TestRestrictAnnotationsDiagnostics:
    def test_diagnostics_include_expected_found_fix_hint_line_and_column(self) -> None:
        result = check(
            """
            from typing import Any

            def handle(payload: dict[str, Any]) -> None:
                pass
            """,
            expected=True,
        )

        assert len(result) == 1
        diagnostic = result[0]

        assert diagnostic.predicate_name == "restrictAnnotations"
        assert diagnostic.line == 3
        assert diagnostic.column == 21
        assert diagnostic.expected == "named record type (pydantic model, TypedDict, or dataclass)"
        assert diagnostic.found == "dict[str, Any]"
        assert diagnostic.fix_hint == (
            "Define a named type (pydantic model, TypedDict, or dataclass) for this record "
            "instead of an anonymous mapping."
        )

    def test_nested_subscript_diagnostic_uses_nested_occurrence_position(self) -> None:
        result = check(
            """
            from typing import Any

            def handle(payload: list[dict[str, Any]]) -> None:
                pass
            """
        )

        assert len(result) == 1
        assert result[0].found == "dict[str, Any]"
        assert result[0].line == 3
        assert result[0].column == 26

    def test_convention_name_and_severity_are_propagated(self) -> None:
        result = check_restrict_annotations(
            expected=True,
            context=context(),
            structure=parse_source(
                """
                from typing import Any

                def handle(payload: dict[str, Any]) -> None:
                    pass
                """
            ),
            convention_name="no-anonymous-records",
            severity="warning",
        )

        assert len(result) == 1
        assert result[0].convention_name == "no-anonymous-records"
        assert result[0].severity == "warning"
