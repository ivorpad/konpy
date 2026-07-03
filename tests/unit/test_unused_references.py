from __future__ import annotations

import ast
import textwrap

from konpy.unused.references import (
    PythonRefSource,
    RefStats,
    build_reference_index,
)


def source(module_path: str, code: str, *, is_test: bool = False) -> PythonRefSource:
    tree = ast.parse(textwrap.dedent(code).strip() + "\n")
    return PythonRefSource(module_path=module_path, tree=tree, is_test=is_test)


def build(*sources: PythonRefSource, entrypoints: list[str] | None = None) -> dict[str, RefStats]:
    return build_reference_index(
        python_sources=list(sources),
        entrypoint_texts=entrypoints or [],
    )


class TestNameReferences:
    def test_load_names_are_referenced(self) -> None:
        index = build(source("src/a.py", "def f():\n    return other()"))

        assert index["other"].prod == 1

    def test_definition_binding_does_not_self_reference(self) -> None:
        index = build(source("src/a.py", "VALUE = 1"))

        assert "VALUE" not in index

    def test_reassignment_and_reads_count(self) -> None:
        index = build(source("src/a.py", "VALUE = 1\nprint(VALUE)"))

        assert index["VALUE"].prod == 1

    def test_augmented_assignment_target_counts(self) -> None:
        index = build(source("src/a.py", "total = 0\ntotal += 1"))

        assert index["total"].prod == 1


class TestAttributeAndImportReferences:
    def test_attribute_access_counts(self) -> None:
        index = build(source("src/a.py", "obj.method()"))

        assert index["method"].prod == 1

    def test_from_import_names_count(self) -> None:
        index = build(source("src/a.py", "from src.other import handler"))

        assert index["handler"].prod == 1

    def test_keyword_argument_names_do_not_count(self) -> None:
        index = build(source("src/a.py", "call(keyword_name=1)"))

        assert "keyword_name" not in index


class TestStringReferences:
    def test_dotted_string_tokens_count(self) -> None:
        index = build(source("src/a.py", 'path = "src.lambda_function.handler"'))

        assert index["handler"].prod == 1
        assert index["lambda_function"].prod == 1

    def test_single_char_tokens_ignored(self) -> None:
        index = build(source("src/a.py", 'x = "a b c"'))

        assert "a" not in index


class TestCategories:
    def test_test_references_tracked_separately(self) -> None:
        index = build(
            source("src/a.py", "prod_use()"),
            source("tests/test_a.py", "test_use()", is_test=True),
        )

        assert index["prod_use"].prod == 1
        assert index["prod_use"].test == 0
        assert index["test_use"].test == 1
        assert index["test_use"].prod == 0

    def test_entrypoint_tokens_tracked(self) -> None:
        index = build(entrypoints=['CMD ["src.app.handler"]'])

        assert index["handler"].entrypoint == 1

    def test_defining_modules_records_referencing_files(self) -> None:
        index = build(
            source("src/a.py", "shared()"),
            source("src/b.py", "shared()"),
        )

        assert index["shared"].defining_modules == frozenset({"src/a.py", "src/b.py"})


class TestSelfReference:
    def test_all_listing_counts_as_reference(self) -> None:
        index = build(source("src/a.py", 'def widget():\n    pass\n\n__all__ = ["widget"]'))

        assert index["widget"].prod == 1
