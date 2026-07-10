from __future__ import annotations

import textwrap
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field

import pytest

from konpy.config.schema import RestrictDuplicateFunctionsOptionsV1
from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_duplicate_functions import (
    DEFAULT_MIN_STATEMENTS,
    check_restrict_duplicate_functions,
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
    return check_restrict_duplicate_functions(
        expected=expected,
        context=_context(path, scope),
        structure=scope.structures[path],
    )


_DUPLICATE_A = """
def canonical(value):
    total = value + 1
    doubled = total * 2
    if doubled:
        return doubled
    return 0
"""

_DUPLICATE_B = """
def duplicate(item):
    result = item + 1
    doubled = result * 2
    if doubled:
        return doubled
    return 0
"""


class TestRestrictDuplicateFunctionsDefaults:
    def test_reports_only_non_canonical_duplicate_in_current_file(self) -> None:
        result = _check(
            path="src/b.py",
            sources={
                "src/a.py": _DUPLICATE_A,
                "src/b.py": _DUPLICATE_B,
            },
        )

        assert len(result) == 1
        assert result[0].file_path == "src/b.py"
        assert result[0].line == 1
        assert result[0].found == "duplicate of src/a.py::canonical"

    def test_canonical_file_gets_no_diagnostic(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": _DUPLICATE_A,
                "src/b.py": _DUPLICATE_B,
            },
        )

        assert result == []

    def test_default_min_statements_skips_small_helpers(self) -> None:
        result = _check(
            path="src/b.py",
            sources={
                "src/a.py": """
                    def one(value):
                        total = value + 1
                        doubled = total * 2
                        return doubled
                """,
                "src/b.py": """
                    def two(item):
                        result = item + 1
                        doubled = result * 2
                        return doubled
                """,
            },
        )

        assert result == []

    def test_min_statements_option_can_lower_threshold(self) -> None:
        result = _check(
            path="src/b.py",
            sources={
                "src/a.py": """
                    def one(value):
                        total = value + 1
                        doubled = total * 2
                        return doubled
                """,
                "src/b.py": """
                    def two(item):
                        result = item + 1
                        doubled = result * 2
                        return doubled
                """,
            },
            expected={"minStatements": 3},
        )

        assert [item.found for item in result] == ["duplicate of src/a.py::one"]

    def test_public_only_true_skips_private_functions(self) -> None:
        result = _check(
            path="src/b.py",
            sources={
                "src/a.py": _DUPLICATE_A.replace("canonical", "_canonical"),
                "src/b.py": _DUPLICATE_B.replace("duplicate", "_duplicate"),
            },
            expected={"publicOnly": True},
        )

        assert result == []

    def test_allow_names_matches_file_qualified_label(self) -> None:
        result = _check(
            path="src/b.py",
            sources={
                "src/a.py": _DUPLICATE_A,
                "src/b.py": _DUPLICATE_B,
            },
            expected={"allowNames": ["src/b.py::duplicate"]},
        )

        assert result == []


class TestRestrictDuplicateFunctionsDiagnostics:
    def test_same_file_reports_only_non_canonical_later_occurrence(self) -> None:
        result = _check(
            path="src/a.py",
            sources={
                "src/a.py": f"{_DUPLICATE_A}\n{_DUPLICATE_B}",
            },
        )

        assert len(result) == 1
        assert result[0].found == "duplicate of src/a.py::canonical"
        assert result[0].line == 9

    def test_diagnostics_include_expected_found_fix_hint_line_and_column(self) -> None:
        scope = _scope(
            {
                "src/a.py": _DUPLICATE_A,
                "src/b.py": _DUPLICATE_B,
            }
        )
        result = check_restrict_duplicate_functions(
            expected=True,
            context=_context("src/b.py", scope),
            structure=scope.structures["src/b.py"],
            convention_name="no-duplicate-functions",
            severity="warning",
        )

        assert len(result) == 1
        diagnostic = result[0]
        assert diagnostic.predicate_name == "restrictDuplicateFunctions"
        assert diagnostic.convention_name == "no-duplicate-functions"
        assert diagnostic.severity == "warning"
        assert diagnostic.line == 1
        assert diagnostic.column == 1
        assert diagnostic.expected == "unique function implementation"
        assert diagnostic.found == "duplicate of src/a.py::canonical"
        assert diagnostic.fix_hint == (
            "Extract the shared implementation into one helper and call it from the "
            "duplicate functions, or make the implementations meaningfully different."
        )

    def test_requires_cross_file_scope(self) -> None:
        with pytest.raises(ValueError, match="requires a cross-file scope"):
            check_restrict_duplicate_functions(
                expected=True,
                context=_context("src/a.py", None),
                structure=_parse(_DUPLICATE_A, "src/a.py"),
            )


class TestRestrictDuplicateFunctionsDefaultDrift:
    def test_schema_defaults_match_predicate_constants(self) -> None:
        options = RestrictDuplicateFunctionsOptionsV1()

        assert options.minStatements == DEFAULT_MIN_STATEMENTS
