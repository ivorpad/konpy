"""Tests for the `restrictFileLength` predicate."""

from __future__ import annotations

import pytest

from konpy.config.schema import RestrictFileLengthOptionsV1
from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.restrict_file_length import (
    DEFAULT_MAX_LINES,
    check_restrict_file_length,
)


def _context(path: str) -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders={},
        file_system=FakeFileSystem(),
        base_path=path.rsplit("/", 1)[0],
    )


def _fs(path: str, content: str) -> FakeFileSystem:
    return FakeFileSystem(contents={path: content})


class TestRestrictFileLength:
    def test_file_over_the_limit_is_flagged(self) -> None:
        diagnostics = check_restrict_file_length(
            expected={"maxLines": 3},
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", "a = 1\nb = 2\nc = 3\nd = 4\n"),
        )

        assert len(diagnostics) == 1
        diagnostic = diagnostics[0]
        assert diagnostic.predicate_name == "restrictFileLength"
        assert diagnostic.message == "File has 4 lines (max 3)"
        assert diagnostic.line == 4
        assert diagnostic.expected == "at most 3 lines"
        assert diagnostic.found == "4 lines"
        assert diagnostic.fix_hint is not None

    def test_file_at_the_limit_is_silent(self) -> None:
        diagnostics = check_restrict_file_length(
            expected={"maxLines": 3},
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", "a = 1\nb = 2\nc = 3\n"),
        )

        assert diagnostics == []

    def test_trailing_newline_does_not_count_as_a_line(self) -> None:
        # Three lines with and without a trailing newline are the same length.
        with_newline = check_restrict_file_length(
            expected={"maxLines": 2},
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", "a = 1\nb = 2\nc = 3\n"),
        )
        without_newline = check_restrict_file_length(
            expected={"maxLines": 2},
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", "a = 1\nb = 2\nc = 3"),
        )

        assert [d.found for d in with_newline] == ["3 lines"]
        assert [d.found for d in without_newline] == ["3 lines"]

    def test_true_uses_the_default_limit(self) -> None:
        over = "\n".join(f"x{i} = {i}" for i in range(DEFAULT_MAX_LINES + 1)) + "\n"

        diagnostics = check_restrict_file_length(
            expected=True,
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", over),
        )

        assert len(diagnostics) == 1
        assert diagnostics[0].expected == f"at most {DEFAULT_MAX_LINES} lines"

    def test_options_model_value_is_honored(self) -> None:
        diagnostics = check_restrict_file_length(
            expected=RestrictFileLengthOptionsV1(maxLines=1),
            context=_context("src/mod.py"),
            file_system=_fs("src/mod.py", "a = 1\nb = 2\n"),
        )

        assert len(diagnostics) == 1

    def test_unreadable_file_is_silent(self) -> None:
        diagnostics = check_restrict_file_length(
            expected=True,
            context=_context("src/missing.py"),
            file_system=FakeFileSystem(),
        )

        assert diagnostics == []


class TestRestrictFileLengthDefaultDrift:
    def test_schema_default_matches_predicate_constant(self) -> None:
        assert RestrictFileLengthOptionsV1().maxLines == DEFAULT_MAX_LINES


class TestMustOnly:
    def test_must_not_is_rejected_by_the_schema(self) -> None:
        from konpy.config.schema import MustBlockV1

        with pytest.raises(ValueError, match="only supported"):
            MustBlockV1.model_validate({"mustNot": {"restrictFileLength": True}})
