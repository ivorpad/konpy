from __future__ import annotations

from typing import Any

from konsistent.infer.heuristics.barrel_usage import mine
from konsistent.infer.models import InferFileRecord
from konsistent.python_ast.structure import NonBarrelStatementInfo, PyFileStructure, SourcePosition

_POS = SourcePosition(line=1, column=0)


def make_structure(non_barrel: tuple[NonBarrelStatementInfo, ...] = ()) -> PyFileStructure:
    defaults: dict[str, Any] = {
        "classes": (),
        "constants": (),
        "declaration_symbols": (),
        "default_export_symbols": (),
        "docstring_targets": (),
        "exports": (),
        "function_annotation_targets": (),
        "functions": (),
        "import_sources": (),
        "imports": (),
        "interfaces": (),
        "named_export_symbols": (),
        "non_barrel_statements": non_barrel,
        "type_aliases": (),
        "all_names": None,
        "all_is_dynamic": False,
    }
    return PyFileStructure(**defaults)


def make_record(
    path: str, *, non_barrel: tuple[NonBarrelStatementInfo, ...] = ()
) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[:-3]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=stem,
        is_test=False,
        is_init=basename == "__init__.py",
        structure=make_structure(non_barrel),
    )


class TestBarrelUsage:
    def test_group_with_one_violator(self) -> None:
        records = [
            make_record("src/a/__init__.py"),
            make_record("src/b/__init__.py"),
            make_record("src/c/__init__.py"),
            make_record(
                "src/d/__init__.py",
                non_barrel=(NonBarrelStatementInfo(kind="declaration", pos=_POS),),
            ),
        ]

        result = mine(records, min_confidence=0.5, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.support == 3
        assert proposal.total == 4
        assert proposal.convention["must"] == {"areBarrelFiles": True}
        assert proposal.convention["paths"] == "src/**/__init__.py"
        assert proposal.violators == ["src/d/__init__.py"]

    def test_below_min_support_is_skipped(self) -> None:
        records = [make_record("src/a/__init__.py")]

        result = mine(records, min_confidence=0.5, min_support=3)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "below-min-support"
