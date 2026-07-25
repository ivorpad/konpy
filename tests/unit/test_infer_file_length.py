from __future__ import annotations

from konpy.infer.heuristics.file_length import mine
from konpy.infer.models import InferFileRecord
from konpy.predicates.restrict_file_length import DEFAULT_MAX_LINES
from konpy.python_ast.parser import parse_file_structure


def _record(path: str, line_count: int, *, is_test: bool = False) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=basename[:-3],
        is_test=is_test,
        is_init=basename == "__init__.py",
        structure=parse_file_structure("x = 1\n", path),
        line_count=line_count,
    )


class TestFileLengthInfer:
    def test_clean_scope_proposes_warning_convention(self) -> None:
        records = [_record(f"src/file_{index}.py", 50) for index in range(3)]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert result.skipped == []
        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.scope == "src"
        assert proposal.support == 3
        assert proposal.convention["severity"] == "warning"
        assert proposal.convention["paths"] == "src/**/*.py"
        assert proposal.convention["must"] == {"restrictFileLength": True}

    def test_over_long_file_skips_with_existing_violations(self) -> None:
        records = [
            _record("src/small.py", 50),
            _record("src/big.py", DEFAULT_MAX_LINES + 1),
            _record("src/other.py", 10),
        ]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "existing-violations"
        assert result.skipped[0].violators == ["src/big.py"]

    def test_file_at_exactly_the_limit_is_clean(self) -> None:
        records = [_record(f"src/file_{index}.py", DEFAULT_MAX_LINES) for index in range(3)]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert len(result.proposals) == 1
        assert result.skipped == []

    def test_min_support_gate_skips_before_clean_ratchet(self) -> None:
        records = [_record("src/only.py", 10)]

        result = mine(records, min_confidence=0.0, min_support=3)

        assert result.proposals == []
        assert result.skipped[0].reason == "below-min-support"

    def test_test_files_are_ignored(self) -> None:
        records = [
            _record("src/a.py", 10),
            _record("src/b.py", 20),
            _record("src/c.py", 30),
            _record("tests/test_big.py", DEFAULT_MAX_LINES + 100, is_test=True),
        ]

        result = mine(records, min_confidence=1.0, min_support=3)

        assert len(result.proposals) == 1
        assert result.proposals[0].scope == "src"
