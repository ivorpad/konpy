"""Zero-config codebase report assembly (M21 phase 1).

Bare `konpy` runs this: unused-code detection, cross-file duplication, and
docstring/annotation coverage over `**/*.py` at engine defaults, with no
`konpy.json` required — plus a conventions summary when a config is present.
Rendering lives in `konpy.core._report_render`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path

from konpy.config.errors import Err
from konpy.config.loader import load_config_runtime
from konpy.config.schema import UnusedCodeV1
from konpy.core._report_duplication import _duplication
from konpy.core._report_generated import apply_fernignore, is_generated_source
from konpy.core._report_model import (
    ReportConventions,
    ReportCoverage,
    ReportData,
    ReportFunctionGroup,
    ReportLiteralGroup,
)
from konpy.core.count_lines import count_physical_lines
from konpy.core.filesystem import FileSystem
from konpy.core.runner import run
from konpy.python_ast import parse_file_structure
from konpy.python_ast.quiet_parse import quiet_parse
from konpy.python_ast.structure import PyFileStructure
from konpy.unused._engine_files import _python_files
from konpy.unused.engine import (
    DEFAULT_EXCLUDE,
    DEFAULT_INCLUDE,
    DEFAULT_TEST_GLOBS,
    run_unused_code_with_metadata,
)

# Aliases of the unused-engine defaults so the report and the engine can
# never drift on what counts as scannable.
DEFAULT_REPORT_INCLUDE: tuple[str, ...] = DEFAULT_INCLUDE
DEFAULT_REPORT_EXCLUDE: tuple[str, ...] = DEFAULT_EXCLUDE


def _collect_structures(
    file_system: FileSystem,
    source_cache: dict[str, str],
    exclude: Sequence[str] = (),
) -> tuple[dict[str, PyFileStructure], set[str], set[str], int, int]:
    """Parse every non-excluded Python file, filling `source_cache` as it reads.

    `exclude` globs are additive on top of `DEFAULT_REPORT_EXCLUDE`, matching
    how the unused engine composes caller excludes over its own defaults.

    Returns (structures, test paths, generated paths, loc, skipped).
    """
    included = set(_python_files(file_system, DEFAULT_REPORT_INCLUDE))
    excluded = set(file_system.glob([*DEFAULT_REPORT_EXCLUDE, *exclude]))
    test_paths = set(_python_files(file_system, DEFAULT_TEST_GLOBS))

    structures: dict[str, PyFileStructure] = {}
    generated: set[str] = set()
    loc = 0
    skipped = 0
    for path in sorted(included - excluded):
        try:
            source = file_system.read_file(path)
            quiet_parse(source, filename=path)
        except (OSError, UnicodeDecodeError, SyntaxError):
            skipped += 1
            continue
        source_cache[path] = source
        loc += count_physical_lines(source)
        structures[path] = parse_file_structure(source, path)
        if is_generated_source(source):
            generated.add(path)

    generated = apply_fernignore(file_system, generated)
    return structures, test_paths & set(structures), generated, loc, skipped


def _coverage(structures: dict[str, PyFileStructure], skip_paths: set[str]) -> ReportCoverage:
    """Count docstring and annotation coverage, skipping test and generated files."""
    counts = {"module": [0, 0], "class": [0, 0], "function": [0, 0]}
    annotated, annotatable = 0, 0

    for path, structure in structures.items():
        if path in skip_paths:
            continue
        for target in structure.docstring_targets:
            if not target.is_public:
                continue
            counts[target.kind][1] += 1
            counts[target.kind][0] += int(target.has_docstring)
        for function in structure.function_annotation_targets:
            if not function.is_public:
                continue
            annotatable += 1
            fully = function.return_type is not None and all(
                param.type_name is not None for param in function.params
            )
            annotated += int(fully)

    return ReportCoverage(
        module_docs=tuple(counts["module"]),
        class_docs=tuple(counts["class"]),
        function_docs=tuple(counts["function"]),
        annotated_functions=(annotated, annotatable),
    )


def _conventions(file_system: FileSystem, config_path: Path) -> ReportConventions:
    """Run the configured conventions when konpy.json exists; summarize the outcome."""
    if not config_path.is_file():
        return ReportConventions(
            status="missing",
            files_checked=0,
            errors=0,
            warnings=0,
            top_diagnostics=(),
            error_text=None,
        )

    loaded = load_config_runtime(config_path=config_path)
    if isinstance(loaded, Err):
        return ReportConventions(
            status="invalid",
            files_checked=0,
            errors=0,
            warnings=0,
            top_diagnostics=(),
            error_text=loaded.error,
        )

    result = run(
        config=loaded.value.config,
        file_system=file_system,
        predicate_registry=loaded.value.predicate_registry,
    )
    errors = sum(1 for d in result.diagnostics if d.severity == "error")
    warnings = len(result.diagnostics) - errors
    ordered = sorted(
        result.diagnostics,
        key=lambda d: (d.severity != "error", d.file_path, d.line or 0),
    )
    return ReportConventions(
        status="clean" if not result.diagnostics else "violations",
        files_checked=result.files_checked,
        errors=errors,
        warnings=warnings,
        top_diagnostics=tuple(ordered),
        error_text=None,
    )


def assemble_report(
    *,
    file_system: FileSystem,
    config_path: Path,
    exclude: Sequence[str] = (),
) -> ReportData:
    """Run every zero-config analysis lane and return the assembled report data.

    `exclude` globs drop matching paths from every analysis lane and from the
    file/LOC header, so a report scoped past vendored or generated trees stays
    internally consistent. The conventions lane is scoped by `konpy.json`
    instead and is unaffected.
    """
    start = time.perf_counter()

    source_cache: dict[str, str] = {}
    structures, test_paths, generated, loc, skipped = _collect_structures(
        file_system, source_cache, exclude
    )
    coverage = _coverage(structures, test_paths | generated)
    literal_groups, function_groups = _duplication(structures, test_paths, generated)
    # DEFAULT_EXCLUDE is applied by the engine itself; sharing the source
    # cache keeps this from re-reading every file `_collect_structures` read.
    unused = run_unused_code_with_metadata(
        config=UnusedCodeV1(),
        file_system=file_system,
        source_cache=source_cache,
        exclude=list(exclude) or None,
        reference_only=sorted(generated),
    )
    conventions = _conventions(file_system, config_path)

    return ReportData(
        files=len(structures),
        test_files=len(test_paths),
        generated_files=len(generated),
        loc=loc,
        skipped_unparsable=skipped,
        unused=tuple(unused.diagnostics),
        literal_groups=literal_groups,
        function_groups=function_groups,
        coverage=coverage,
        conventions=conventions,
        duration_ms=(time.perf_counter() - start) * 1000,
    )


__all__ = [
    "DEFAULT_REPORT_EXCLUDE",
    "DEFAULT_REPORT_INCLUDE",
    "ReportConventions",
    "ReportCoverage",
    "ReportData",
    "ReportFunctionGroup",
    "ReportLiteralGroup",
    "assemble_report",
]
