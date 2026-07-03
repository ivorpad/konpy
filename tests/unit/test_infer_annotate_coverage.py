from __future__ import annotations

from typing import Any

from konpy.infer.heuristics.annotate_coverage import mine
from konpy.infer.models import InferFileRecord
from konpy.python_ast.structure import (
    FunctionAnnotationInfo,
    ParamInfo,
    PyFileStructure,
    SourcePosition,
    TypeAnnotationInfo,
)

_POS = SourcePosition(line=1, column=0)
_TYPE = TypeAnnotationInfo(base_name="int", text="int")


def param(name: str, *, annotated: bool) -> ParamInfo:
    return ParamInfo(name=name, type_name=_TYPE if annotated else None)


def function(
    name: str,
    *,
    is_public: bool = True,
    params: tuple[ParamInfo, ...] = (),
    return_annotated: bool = False,
) -> FunctionAnnotationInfo:
    return FunctionAnnotationInfo(
        name=name,
        qualified_name=name,
        is_public=is_public,
        params=params,
        pos=_POS,
        return_type=_TYPE if return_annotated else None,
    )


def make_structure(targets: tuple[FunctionAnnotationInfo, ...]) -> PyFileStructure:
    defaults: dict[str, Any] = {
        "classes": (),
        "constants": (),
        "declaration_symbols": (),
        "default_export_symbols": (),
        "docstring_targets": (),
        "exports": (),
        "function_annotation_targets": targets,
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
    return PyFileStructure(**defaults)


def make_record(path: str, *targets: FunctionAnnotationInfo) -> InferFileRecord:
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    basename = path.rsplit("/", 1)[-1]
    stem = basename[:-3]
    return InferFileRecord(
        path=path,
        directory=directory,
        stem=stem,
        is_test=False,
        is_init=False,
        structure=make_structure(targets),
    )


class TestAnnotateCoverage:
    def test_params_measured_per_parameter(self) -> None:
        records = [
            make_record(
                "src/mod.py",
                function(
                    "f",
                    params=(
                        param("a", annotated=True),
                        param("b", annotated=True),
                        param("c", annotated=True),
                    ),
                    return_annotated=True,
                ),
            )
        ]

        result = mine(records, min_confidence=0.9, min_support=1)

        proposal = result.proposals[0]
        assert proposal.convention["must"]["annotateFunctions"]["params"] is True
        assert proposal.convention["must"]["annotateFunctions"]["returns"] is True

    def test_only_returns_clears_threshold(self) -> None:
        records = [
            make_record(
                f"src/mod{i}.py",
                function(
                    f"f{i}",
                    params=(param("a", annotated=False),),
                    return_annotated=True,
                ),
            )
            for i in range(3)
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        proposal = result.proposals[0]
        assert proposal.convention["must"]["annotateFunctions"] == {
            "returns": True,
            "params": False,
            "publicOnly": True,
        }
        params_skips = [s for s in result.skipped if s.detail == "params"]
        assert len(params_skips) == 1

    def test_public_only_excludes_private_functions(self) -> None:
        records = [
            make_record(
                "src/mod.py",
                function(
                    "public_fn",
                    is_public=True,
                    params=(param("a", annotated=True),),
                    return_annotated=True,
                ),
                function(
                    "_private_fn",
                    is_public=False,
                    params=(param("a", annotated=False),),
                    return_annotated=False,
                ),
            )
        ]

        result = mine(records, min_confidence=0.9, min_support=1)

        proposal = result.proposals[0]
        assert proposal.support == 2
        assert proposal.total == 2
