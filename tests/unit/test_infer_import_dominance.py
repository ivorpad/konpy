from __future__ import annotations

from typing import Any

from konpy.infer.heuristics.import_dominance import mine
from konpy.infer.models import InferFileRecord
from konpy.python_ast.structure import ImportSourceInfo, PyFileStructure, SourcePosition

_POS = SourcePosition(line=1, column=0)


def source(*, level: int, is_type: bool = False) -> ImportSourceInfo:
    return ImportSourceInfo(from_="mod", is_type=is_type, pos=_POS, level=level)


def make_structure(sources: tuple[ImportSourceInfo, ...]) -> PyFileStructure:
    defaults: dict[str, Any] = {
        "class_attributes": (),
        "classes": (),
        "constants": (),
        "declaration_symbols": (),
        "default_export_symbols": (),
        "docstring_targets": (),
        "exports": (),
        "function_annotation_targets": (),
        "functions": (),
        "function_fingerprints": (),
        "import_sources": sources,
        "imports": (),
        "interfaces": (),
        "named_export_symbols": (),
        "non_barrel_statements": (),
        "string_literals": (),
        "type_aliases": (),
        "decorators": (),
        "call_sites": (),
        "base_class_refs": (),
        "scoped_imports": (),
        "all_names": None,
        "all_is_dynamic": False,
    }
    return PyFileStructure(**defaults)


def make_record(path: str, *sources: ImportSourceInfo) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[:-3]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=stem,
        is_test=False,
        is_init=False,
        structure=make_structure(sources),
    )


class TestImportDominance:
    def test_prefers_absolute_proposal(self) -> None:
        records = [
            make_record("src/a.py", source(level=0)),
            make_record("src/b.py", source(level=0)),
            make_record("src/c.py", source(level=0)),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.convention["mustNot"] == {
            "importFromCurrentDir": True,
            "importFromParents": True,
        }
        assert proposal.convention["paths"] == ["src/**/*.py", "!src/**/__init__.py"]
        assert "must" not in proposal.convention

    def test_files_with_zero_imports_excluded_from_denominator(self) -> None:
        records = [
            make_record("src/a.py", source(level=0)),
            make_record("src/b.py", source(level=0)),
            make_record("src/c.py", source(level=0)),
            make_record("src/d.py"),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert result.proposals[0].total == 3

    def test_never_proposes_prefers_relative_direction(self) -> None:
        records = [
            make_record("src/a.py", source(level=1)),
            make_record("src/b.py", source(level=1)),
            make_record("src/c.py", source(level=0)),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)
        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "below-min-confidence"

        low_threshold_result = mine(records, min_confidence=0.0, min_support=1)
        assert len(low_threshold_result.proposals) == 1
        assert "must" not in low_threshold_result.proposals[0].convention
        assert low_threshold_result.proposals[0].convention["mustNot"] == {
            "importFromCurrentDir": True,
            "importFromParents": True,
        }
