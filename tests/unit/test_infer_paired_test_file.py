from __future__ import annotations

from typing import Any

from konsistent.infer.heuristics.paired_test_file import mine
from konsistent.infer.models import InferFileRecord
from konsistent.python_ast.structure import PyFileStructure


def make_structure() -> PyFileStructure:
    return PyFileStructure(
        classes=(),
        constants=(),
        declaration_symbols=(),
        default_export_symbols=(),
        docstring_targets=(),
        exports=(),
        function_annotation_targets=(),
        functions=(),
        import_sources=(),
        imports=(),
        interfaces=(),
        named_export_symbols=(),
        non_barrel_statements=(),
        type_aliases=(),
        all_names=None,
        all_is_dynamic=False,
    )


def make_record(path: str, *, is_test: bool = False, is_init: bool = False) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[:-3]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=stem,
        is_test=is_test,
        is_init=is_init,
        structure=make_structure(),
    )


def find(result: Any, scope: str) -> Any:
    return next(p for p in result if p.scope == scope)


class TestPairedTestFile:
    def test_full_match_produces_proposal(self) -> None:
        records = [
            make_record("src/services/user_service.py"),
            make_record("src/services/order_service.py"),
            make_record("src/services/billing_service.py"),
            make_record("tests/test_user_service.py", is_test=True),
            make_record("tests/test_order_service.py", is_test=True),
            make_record("tests/test_billing_service.py", is_test=True),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.support == 3
        assert proposal.total == 3
        assert proposal.convention["must"] == {"havePairedFile": "tests/test_${name}.py"}
        assert proposal.convention["paths"] == [
            "src/services/{name}.py",
            "!src/services/__init__.py",
        ]

    def test_unmatched_file_is_a_violator(self) -> None:
        records = [
            make_record("src/services/user_service.py"),
            make_record("src/services/order_service.py"),
            make_record("src/services/billing_service.py"),
            make_record("tests/test_user_service.py", is_test=True),
            make_record("tests/test_order_service.py", is_test=True),
        ]

        result = mine(records, min_confidence=0.5, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.support == 2
        assert proposal.total == 3
        assert proposal.violators == ["src/services/billing_service.py"]

    def test_higher_count_template_wins(self) -> None:
        records = [
            make_record("src/a.py"),
            make_record("src/b.py"),
            make_record("src/c.py"),
            make_record("tests/test_a.py", is_test=True),
            make_record("tests/test_b.py", is_test=True),
            make_record("tests/unit/test_c.py", is_test=True),
        ]

        result = mine(records, min_confidence=0.5, min_support=3)

        proposal = find(result.proposals, "src")
        assert proposal.convention["must"] == {"havePairedFile": "tests/test_${name}.py"}
        assert proposal.support == 2
        assert proposal.violators == ["src/c.py"]

    def test_tie_resolves_to_lexicographically_smaller_template(self) -> None:
        records = [
            make_record("src/a.py"),
            make_record("src/b.py"),
            make_record("tests/test_a.py", is_test=True),
            make_record("tests/unit/test_b.py", is_test=True),
        ]

        result = mine(records, min_confidence=0.0, min_support=2)

        proposal = find(result.proposals, "src")
        assert proposal.convention["must"] == {"havePairedFile": "tests/test_${name}.py"}
        assert proposal.support == 1
        assert proposal.violators == ["src/b.py"]

    def test_directory_with_zero_test_pairs_emits_nothing(self) -> None:
        records = [make_record("src/legacy/d.py")]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals == []
        assert result.skipped == []

    def test_init_file_never_counted_as_production_file(self) -> None:
        records = [
            make_record("src/pkg/__init__.py", is_init=True),
            make_record("src/pkg/a.py"),
            make_record("tests/test_a.py", is_test=True),
        ]

        result = mine(records, min_confidence=0.9, min_support=1)

        assert len(result.proposals) == 1
        assert result.proposals[0].total == 1
