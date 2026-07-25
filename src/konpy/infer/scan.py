"""Filesystem/AST scanning for `konpy infer` (M15 convention mining)."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from konpy.core.count_lines import count_physical_lines
from konpy.core.filesystem import FileSystem
from konpy.infer.models import InferFileRecord
from konpy.python_ast import parse_file_structure


def collect_file_records(
    *,
    file_system: FileSystem,
    include: Sequence[str],
    exclude: Sequence[str],
    test_globs: Sequence[str],
) -> tuple[list[InferFileRecord], int, int]:
    """Returns ``(records, files_skipped_unparsable, files_skipped_unreadable)``."""

    included = {
        path
        for path in file_system.glob(list(include))
        if path.endswith(".py") and not file_system.is_directory(path)
    }
    excluded = set(file_system.glob(list(exclude))) if exclude else set()
    test_matched = {
        path
        for path in file_system.glob(list(test_globs))
        if path.endswith(".py") and not file_system.is_directory(path)
    }

    candidate_paths = sorted(included - excluded)

    records: list[InferFileRecord] = []
    files_skipped_unparsable = 0
    files_skipped_unreadable = 0

    for path in candidate_paths:
        try:
            source = file_system.read_file(path)
        except (OSError, UnicodeDecodeError):
            files_skipped_unreadable += 1
            continue

        try:
            ast.parse(source, filename=path)
        except SyntaxError:
            files_skipped_unparsable += 1
            continue

        structure = parse_file_structure(source, path)

        directory = path.rsplit("/", 1)[0] if "/" in path else ""
        basename = path.rsplit("/", 1)[-1]
        stem = basename[:-3]
        is_test = path in test_matched
        is_init = basename == "__init__.py"

        line_count = count_physical_lines(source)
        records.append(
            InferFileRecord(
                path=path,
                directory=directory,
                stem=stem,
                is_test=is_test,
                is_init=is_init,
                structure=structure,
                line_count=line_count,
            )
        )

    return records, files_skipped_unparsable, files_skipped_unreadable


__all__ = ["collect_file_records"]
