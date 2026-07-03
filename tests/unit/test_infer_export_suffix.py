from __future__ import annotations

from typing import Any

from konpy.infer.heuristics.export_suffix import mine
from konpy.infer.models import InferFileRecord
from konpy.python_ast.structure import ExportInfo, PyFileStructure, SourcePosition

_POS = SourcePosition(line=1, column=0)


def make_structure(**overrides: Any) -> PyFileStructure:
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
        "non_barrel_statements": (),
        "type_aliases": (),
        "all_names": None,
        "all_is_dynamic": False,
    }
    defaults.update(overrides)
    return PyFileStructure(**defaults)


def make_record(
    path: str,
    *,
    is_test: bool = False,
    is_init: bool = False,
    exports: tuple[ExportInfo, ...] = (),
) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[:-3]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=stem,
        is_test=is_test,
        is_init=is_init,
        structure=make_structure(exports=exports),
    )


def export(name: str, *, kind: str = "class") -> ExportInfo:
    return ExportInfo(from_=None, is_type=False, kind=kind, name=name, pos=_POS)


class TestExportSuffix:
    def test_matching_group_is_one_proposal(self) -> None:
        records = [
            make_record("src/services/foo_service.py", exports=(export("FooService"),)),
            make_record("src/services/bar_service.py", exports=(export("BarService"),)),
            make_record("src/services/baz_service.py", exports=(export("BazService"),)),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.support == 3
        assert proposal.total == 3
        assert proposal.convention["must"] == {"exportClasses": ["${name.toPascalCase()}Service"]}
        assert proposal.convention["paths"] == "src/services/{name}_service.py"
        assert proposal.convention_name == "infer-export-suffix-src-services-service"

    def test_one_mismatch_is_a_violator(self) -> None:
        records = [
            make_record("src/services/foo_service.py", exports=(export("FooService"),)),
            make_record("src/services/bar_service.py", exports=(export("BarService"),)),
            make_record("src/services/baz_service.py", exports=(export("WrongName"),)),
        ]

        result = mine(records, min_confidence=0.5, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.support == 2
        assert proposal.total == 3
        assert proposal.violators == ["src/services/baz_service.py"]

    def test_unknown_suffix_token_contributes_to_no_group(self) -> None:
        records = [make_record("src/services/foo_impl.py", exports=(export("FooImpl"),))]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals == []
        assert result.skipped == []

    def test_below_min_support_is_skipped_not_proposed(self) -> None:
        records = [make_record("src/services/x_service.py", exports=(export("XService"),))]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert result.proposals == []
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == "below-min-support"

    def test_multiple_directories_sorted_by_directory_ascending(self) -> None:
        records = [
            make_record("src/zeta/a_service.py", exports=(export("AService"),)),
            make_record("src/zeta/b_service.py", exports=(export("BService"),)),
            make_record("src/zeta/c_service.py", exports=(export("CService"),)),
            make_record("src/alpha/a_service.py", exports=(export("AService"),)),
            make_record("src/alpha/b_service.py", exports=(export("BService"),)),
            make_record("src/alpha/c_service.py", exports=(export("CService"),)),
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        scopes = [proposal.scope for proposal in result.proposals]
        assert scopes == sorted(scopes)
        assert scopes == ["src/alpha", "src/zeta"]

    def test_test_and_init_records_are_excluded(self) -> None:
        records = [
            make_record("src/services/foo_service.py", exports=(export("FooService"),)),
            make_record(
                "src/services/test_bar_service.py", is_test=True, exports=(export("BarService"),)
            ),
            make_record("src/services/__init__.py", is_init=True),
        ]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert len(result.proposals) == 1
        assert result.proposals[0].total == 1

    def test_confidence_exactly_equal_to_threshold_is_included(self) -> None:
        records = [
            make_record("src/services/a_service.py", exports=(export("AService"),)),
            make_record("src/services/b_service.py", exports=(export("BService"),)),
            make_record("src/services/c_service.py", exports=(export("WrongName"),)),
        ]

        result = mine(records, min_confidence=2 / 3, min_support=3)

        assert len(result.proposals) == 1
        assert result.proposals[0].support == 2
        assert result.proposals[0].total == 3
