from __future__ import annotations

import textwrap
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field

import pytest

from konpy.config.schema import RestrictRepeatedLiteralsOptionsV1
from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_repeated_literals import (
    DEFAULT_MAX_OCCURRENCES,
    DEFAULT_MIN_LENGTH,
    check_restrict_repeated_literals,
)
from konpy.python_ast.parser import parse_file_structure
from konpy.python_ast.structure import PyFileStructure


@dataclass
class _Scope:
    paths: tuple[str, ...]
    structures: Mapping[str, PyFileStructure]
    indexes: dict[tuple[tuple[str, ...], Hashable], object] = field(default_factory=dict)

    def get_or_build_index(
        self,
        key: Hashable,
        builder: Callable[[Mapping[str, PyFileStructure]], object],
    ) -> object:
        cache_key = (self.paths, key)
        if cache_key not in self.indexes:
            self.indexes[cache_key] = builder(self.structures)
        return self.indexes[cache_key]


def _parse(source: str, path: str) -> PyFileStructure:
    return parse_file_structure(textwrap.dedent(source).strip() + "\n", path)


def _scope(sources: Mapping[str, str]) -> _Scope:
    structures = {path: _parse(source, path) for path, source in sources.items()}
    return _Scope(paths=tuple(sorted(sources)), structures=structures)


def _context(path: str, scope: _Scope | None) -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders={},
        file_system=FakeFileSystem(),
        base_path=path.rsplit("/", 1)[0],
        cross_file=scope,
    )


def _check(
    *,
    path: str,
    sources: Mapping[str, str],
    expected: object = True,
):
    scope = _scope(sources)
    return check_restrict_repeated_literals(
        expected=expected,
        context=_context(path, scope),
        structure=scope.structures[path],
    )


class TestRestrictRepeatedLiteralsDefaults:
    def test_defaults_allow_two_occurrences(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": 'A = "shared-value"\n',
                "src/b.py": 'B = "shared-value"\n',
            },
        )

        assert result == []

    def test_defaults_flag_every_current_file_occurrence_after_third(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": '''
                    A = "shared-value"
                    B = "shared-value"
                ''',
                "src/b.py": 'C = "shared-value"\n',
            },
        )

        assert [(item.found, item.line, item.column) for item in result] == [
            ("shared-value", 1, 5),
            ("shared-value", 2, 5),
        ]

    def test_min_length_and_max_occurrences_options(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": '''
                    A = "tiny"
                    B = "long-literal"
                ''',
                "src/b.py": '''
                    A = "tiny"
                    B = "long-literal"
                ''',
            },
            expected={"minLength": 8, "maxOccurrences": 1},
        )

        assert [item.found for item in result] == ["long-literal"]

    def test_allow_patterns_skip_matching_values(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": 'A = "shared-value"\n',
                "src/b.py": 'B = "shared-value"\n',
                "src/c.py": 'C = "shared-value"\n',
            },
            expected={"allow": ["shared-*"]},
        )

        assert result == []


class TestRestrictRepeatedLiteralsDiagnostics:
    def test_diagnostics_include_expected_found_fix_hint_line_and_column(self) -> None:
        result = check_restrict_repeated_literals(
            expected=True,
            context=_context(
                "src/a.py",
                _scope(
                    {
                        "src/a.py": 'A = "shared-value"\n',
                        "src/b.py": 'B = "shared-value"\n',
                        "src/c.py": 'C = "shared-value"\n',
                    }
                ),
            ),
            structure=_parse('A = "shared-value"\n', "src/a.py"),
            convention_name="no-repeated-literals",
            severity="warning",
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictRepeatedLiterals"
        assert diagnostic.convention_name == "no-repeated-literals"
        assert diagnostic.severity == "warning"
        assert diagnostic.line == 1
        assert diagnostic.column == 5
        assert diagnostic.expected == "at most 2 occurrence(s) of each string literal"
        assert diagnostic.found == "shared-value"
        assert diagnostic.fix_hint == (
            "Extract the repeated string into a named constant or shared fixture and "
            "reference that name instead."
        )

    def test_requires_cross_file_scope(self) -> None:
        with pytest.raises(ValueError, match="requires a cross-file scope"):
            check_restrict_repeated_literals(
                expected=True,
                context=_context("src/a.py", None),
                structure=_parse('A = "shared-value"\n', "src/a.py"),
            )


class TestRestrictRepeatedLiteralsDefaultDrift:
    def test_schema_defaults_match_predicate_constants(self) -> None:
        options = RestrictRepeatedLiteralsOptionsV1()

        assert options.minLength == DEFAULT_MIN_LENGTH
        assert options.maxOccurrences == DEFAULT_MAX_OCCURRENCES
