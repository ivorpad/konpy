from __future__ import annotations

import textwrap

from konpy.infer.heuristics.duplicate_functions import mine
from konpy.infer.models import InferFileRecord
from konpy.predicates.restrict_duplicate_functions import DEFAULT_MIN_STATEMENTS
from konpy.python_ast.parser import parse_file_structure


def _record(path: str, source: str, *, is_test: bool = False) -> InferFileRecord:
    source_text = textwrap.dedent(source).strip() + "\n"
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=basename[:-3],
        is_test=is_test,
        is_init=basename == "__init__.py",
        structure=parse_file_structure(source_text, path),
    )


def _duplicate_source(name: str, parameter: str) -> str:
    lines = [f"def {name}({parameter}):"]
    if DEFAULT_MIN_STATEMENTS <= 1:
        lines.append(f"    return {parameter}")
        return "\n".join(lines)

    for index in range(DEFAULT_MIN_STATEMENTS - 1):
        lines.append(f"    value_{index} = {parameter} + {index}")
    lines.append(f"    return value_{DEFAULT_MIN_STATEMENTS - 2}")
    return "\n".join(lines)


class TestDuplicateFunctionsInfer:
    def test_clean_scope_proposes_warning_convention(self) -> None:
        records = [
            _record("src/a.py", "def a(value):\n    return value + 1"),
            _record("src/b.py", "def b(value):\n    return value + 2"),
            _record("src/c.py", "def c(value):\n    return value + 3"),
        ]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert result.skipped == []
        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.scope == "src"
        assert proposal.support == 3
        assert proposal.total == 3
        assert proposal.violators == []
        assert proposal.convention["severity"] == "warning"
        assert proposal.convention["paths"] == "src/**/*.py"
        assert proposal.convention["must"] == {"restrictDuplicateFunctions": True}

    def test_dirty_scope_skips_with_existing_violations(self) -> None:
        records = [
            _record("src/a.py", _duplicate_source("canonical", "value")),
            _record("src/b.py", _duplicate_source("duplicate", "item")),
            _record("src/c.py", "def unique(value):\n    return value + 100"),
        ]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "existing-violations"
        assert result.skipped[0].violators == ["src/b.py"]

    def test_min_support_gate_skips_before_clean_ratchet(self) -> None:
        records = [_record("src/only.py", "def only(value):\n    return value")]

        result = mine(records, min_confidence=0.0, min_support=3)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "below-min-support"

    def test_default_min_statements_constant_controls_violation_detection(self) -> None:
        records = [
            _record("src/a.py", "def one(value):\n    return value"),
            _record("src/b.py", "def two(item):\n    return item"),
            _record("src/c.py", "def three(value):\n    return value + 1"),
        ]

        result = mine(records, min_confidence=1.0, min_support=1)

        assert len(result.proposals) == 1
        assert result.skipped == []

    def test_test_files_are_ignored(self) -> None:
        records = [
            _record("src/a.py", "def a(value):\n    return value + 1"),
            _record("src/b.py", "def b(value):\n    return value + 2"),
            _record("src/c.py", "def c(value):\n    return value + 3"),
            _record("tests/test_a.py", _duplicate_source("canonical", "value"), is_test=True),
            _record("tests/test_b.py", _duplicate_source("duplicate", "item"), is_test=True),
        ]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert len(result.proposals) == 1
        assert result.proposals[0].scope == "src"
