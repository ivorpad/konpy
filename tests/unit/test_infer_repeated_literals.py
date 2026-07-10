from __future__ import annotations

import textwrap

from konpy.infer.heuristics.repeated_literals import mine
from konpy.infer.models import InferFileRecord
from konpy.predicates.restrict_repeated_literals import (
    DEFAULT_MAX_OCCURRENCES,
    DEFAULT_MIN_LENGTH,
)
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


class TestRepeatedLiteralsInfer:
    def test_clean_scope_proposes_warning_convention(self) -> None:
        records = [
            _record(f"src/file_{index}.py", f'VALUE = "unique-value-{index}"')
            for index in range(3)
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
        assert proposal.convention["must"] == {"restrictRepeatedLiterals": True}

    def test_dirty_scope_skips_with_existing_violations(self) -> None:
        literal = "x" * DEFAULT_MIN_LENGTH
        records = [
            _record(f"src/file_{index}.py", f'VALUE = "{literal}"')
            for index in range(DEFAULT_MAX_OCCURRENCES + 1)
        ]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "existing-violations"
        assert result.skipped[0].violators == [
            f"src/file_{index}.py" for index in range(DEFAULT_MAX_OCCURRENCES + 1)
        ]

    def test_min_support_gate_skips_before_clean_ratchet(self) -> None:
        records = [_record("src/only.py", 'VALUE = "unique-value"')]

        result = mine(records, min_confidence=0.0, min_support=3)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "below-min-support"

    def test_default_min_length_constant_controls_violation_detection(self) -> None:
        short = "x" * max(0, DEFAULT_MIN_LENGTH - 1)
        records = [
            _record(f"src/file_{index}.py", f'VALUE = "{short}"')
            for index in range(DEFAULT_MAX_OCCURRENCES + 1)
        ]

        result = mine(records, min_confidence=1.0, min_support=1)

        assert len(result.proposals) == 1
        assert result.skipped == []

    def test_test_files_are_ignored(self) -> None:
        literal = "x" * DEFAULT_MIN_LENGTH
        records = [
            _record("src/a.py", 'VALUE = "unique-value"'),
            _record("src/b.py", 'VALUE = "another-value"'),
            _record("src/c.py", 'VALUE = "third-value"'),
            _record("tests/test_a.py", f'VALUE = "{literal}"', is_test=True),
            _record("tests/test_b.py", f'VALUE = "{literal}"', is_test=True),
            _record("tests/test_c.py", f'VALUE = "{literal}"', is_test=True),
        ]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert len(result.proposals) == 1
        assert result.proposals[0].scope == "src"
