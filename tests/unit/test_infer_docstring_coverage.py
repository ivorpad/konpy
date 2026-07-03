from __future__ import annotations

from typing import Any

from konpy.infer.heuristics.docstring_coverage import mine
from konpy.infer.models import InferFileRecord
from konpy.python_ast.structure import DocstringTargetInfo, PyFileStructure, SourcePosition

_POS = SourcePosition(line=1, column=0)


def target(
    kind: str,
    name: str,
    *,
    is_public: bool = True,
    has_docstring: bool,
) -> DocstringTargetInfo:
    return DocstringTargetInfo(
        kind=kind,  # type: ignore[arg-type]
        name=name,
        qualified_name=name,
        is_public=is_public,
        has_docstring=has_docstring,
        pos=_POS,
    )


def make_structure(targets: tuple[DocstringTargetInfo, ...]) -> PyFileStructure:
    defaults: dict[str, Any] = {
        "classes": (),
        "constants": (),
        "declaration_symbols": (),
        "default_export_symbols": (),
        "docstring_targets": targets,
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
    return PyFileStructure(**defaults)


def make_record(path: str, *targets: DocstringTargetInfo) -> InferFileRecord:
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


class TestDocstringCoverage:
    def test_modules_and_classes_pass_but_functions_fail(self) -> None:
        records = [
            make_record(
                f"src/mod{i}.py",
                target("module", f"mod{i}", has_docstring=True),
                target("class", f"C{i}", has_docstring=True),
                target("function", f"f{i}", has_docstring=False),
            )
            for i in range(3)
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.convention["must"]["haveDocstrings"] == {
            "modules": True,
            "classes": True,
            "functions": False,
            "publicOnly": True,
        }
        assert proposal.detail == "modules, classes"

        function_skips = [s for s in result.skipped if s.detail == "functions"]
        assert len(function_skips) == 1
        assert function_skips[0].scope == "src"
        assert function_skips[0].reason is not None

    def test_kind_with_zero_total_is_excluded_entirely(self) -> None:
        records = [
            make_record(
                f"src/mod{i}.py",
                target("module", f"mod{i}", has_docstring=True),
                target("class", f"C{i}", has_docstring=True),
            )
            for i in range(3)
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert not any(s.detail == "functions" for s in result.skipped)
        assert result.proposals[0].detail == "modules, classes"

    def test_all_kinds_below_threshold_yields_no_proposal(self) -> None:
        records = [
            make_record(
                f"src/mod{i}.py",
                target("module", f"mod{i}", has_docstring=i == 0),
                target("class", f"C{i}", has_docstring=i == 0),
                target("function", f"f{i}", has_docstring=i == 0),
            )
            for i in range(3)
        ]

        result = mine(records, min_confidence=0.9, min_support=3)

        assert result.proposals == []
        assert len(result.skipped) == 3
        assert {s.detail for s in result.skipped} == {"modules", "classes", "functions"}

    def test_private_targets_never_count_toward_classes_or_functions(self) -> None:
        records = [
            make_record(
                "src/mod.py",
                target("module", "mod", has_docstring=True),
                target("class", "_Private", is_public=False, has_docstring=False),
                target("function", "_private", is_public=False, has_docstring=False),
            )
        ]

        result = mine(records, min_confidence=0.0, min_support=1)

        assert result.proposals[0].detail == "modules"
        assert not any(s.detail in {"classes", "functions"} for s in result.skipped)
