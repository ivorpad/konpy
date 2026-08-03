"""Zero-config codebase report assembly (M21 phase 1).

Bare `konpy` runs this: unused-code detection, cross-file duplication,
docstring/annotation coverage, and external-tool lanes (ruff, basedpyright,
import-linter) over `**/*.py` at engine defaults, with no `konpy.json`
required — plus a conventions summary when a config is present. Rendering
lives in `konpy.core._report_render`.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from konpy.config.schema import UnusedCodeV1
from konpy.core._report_conventions import configured_conventions, default_conventions
from konpy.core._report_duplication import _duplication
from konpy.core._report_generated import apply_fernignore, is_generated_source
from konpy.core._report_model import (
    ReportConventions,
    ReportCoverage,
    ReportData,
    ReportFunctionGroup,
    ReportLiteralGroup,
    ReportToolLane,
)
from konpy.core._report_tools import Runner, collect_tool_lanes
from konpy.core._report_vendor import VendorClassification, detect_vendor_paths
from konpy.core.count_lines import count_physical_lines
from konpy.core.filesystem import FileSystem
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


@dataclass(frozen=True, kw_only=True)
class _Collected:
    """Everything `_collect_structures` gathers in one pass over the tree."""

    structures: dict[str, PyFileStructure]
    test_paths: set[str]
    generated: set[str]
    loc: int
    skipped: int
    vendor: VendorClassification
    vendor_dropped: frozenset[str]


def _collect_structures(
    file_system: FileSystem,
    source_cache: dict[str, str],
    exclude: Sequence[str] = (),
    *,
    root: Path,
    include_vendored: bool = False,
) -> _Collected:
    """Parse every non-excluded, non-vendored Python file, filling `source_cache` as it reads.

    `exclude` globs are additive on top of `DEFAULT_REPORT_EXCLUDE`, matching
    how the unused engine composes caller excludes over its own defaults.
    Vendor/template/gitignored detection (`detect_vendor_paths`) always runs
    over the remaining candidates so duplicate labeling has it available;
    unless `include_vendored` is set, matched files are dropped here too --
    never parsed, never counted, never attempted -- so they can't inflate the
    unparsable-file count either.
    """
    included = set(_python_files(file_system, DEFAULT_REPORT_INCLUDE))
    excluded = set(file_system.glob([*DEFAULT_REPORT_EXCLUDE, *exclude]))
    candidates = included - excluded
    test_paths = set(_python_files(file_system, DEFAULT_TEST_GLOBS))

    vendor = detect_vendor_paths(root, sorted(candidates))
    vendor_dropped: frozenset[str] = (
        frozenset()
        if include_vendored
        else vendor.template_files | vendor.vendored_files | vendor.gitignored_files
    )

    structures: dict[str, PyFileStructure] = {}
    generated: set[str] = set()
    loc = 0
    skipped = 0
    for path in sorted(candidates - vendor_dropped):
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
    return _Collected(
        structures=structures,
        test_paths=test_paths & set(structures),
        generated=generated,
        loc=loc,
        skipped=skipped,
        vendor=vendor,
        vendor_dropped=vendor_dropped,
    )


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
        module_docs=(counts["module"][0], counts["module"][1]),
        class_docs=(counts["class"][0], counts["class"][1]),
        function_docs=(counts["function"][0], counts["function"][1]),
        annotated_functions=(annotated, annotatable),
    )


def assemble_report(
    *,
    file_system: FileSystem,
    config_path: Path,
    exclude: Sequence[str] = (),
    include_vendored: bool = False,
    tool_runner: Runner = subprocess.run,
    tool_timeout: float = 60.0,
) -> ReportData:
    """Run every zero-config analysis lane and return the assembled report data.

    `exclude` globs drop matching paths from the in-process lanes (unused,
    duplication, coverage) and from the file/LOC header, so a report scoped
    past vendored or generated trees stays internally consistent there.
    Cookiecutter scaffolds, vendored snapshot dirs, and gitignored files are
    detected automatically (`detect_vendor_paths`) and, unless
    `include_vendored` is set, dropped the same way: out of every count, but
    still fed to the unused engine as reference-only sources so hand-written
    code they call stays used. Detection always runs regardless of
    `include_vendored`, so duplicate groups confined to those trees keep
    their label either way. The conventions lane is scoped by `konpy.json`
    instead, and the external-tool lanes (ruff, basedpyright, import-linter)
    run over the whole tree through their own configuration -- neither is
    affected by `exclude` or vendor detection. `tool_runner`/`tool_timeout`
    are forwarded to `collect_tool_lanes` (real subprocesses by default;
    injectable for tests).
    """
    start = time.perf_counter()

    # The external-tool lanes are independent subprocesses over the whole
    # tree; kick them off now and collect the result at the end so their
    # wall-clock overlaps the in-process analysis below instead of adding to
    # it.
    with ThreadPoolExecutor(max_workers=1) as tool_pool:
        tool_lanes_future = tool_pool.submit(
            collect_tool_lanes,
            config_path.parent,
            timeout=tool_timeout,
            runner=tool_runner,
        )

        source_cache: dict[str, str] = {}
        collected = _collect_structures(
            file_system,
            source_cache,
            exclude,
            root=config_path.parent,
            include_vendored=include_vendored,
        )
        coverage = _coverage(collected.structures, collected.test_paths | collected.generated)
        literal_groups, function_groups = _duplication(
            collected.structures,
            collected.test_paths,
            collected.generated,
            template=collected.vendor.template_files,
            vendored=collected.vendor.vendored_files,
        )
        # DEFAULT_EXCLUDE is applied by the engine itself; sharing the source
        # cache keeps this from re-reading every file `_collect_structures` read.
        unused = run_unused_code_with_metadata(
            config=UnusedCodeV1(),
            file_system=file_system,
            source_cache=source_cache,
            exclude=list(exclude) or None,
            reference_only=sorted(collected.generated | collected.vendor_dropped),
        )
        conventions = configured_conventions(file_system, config_path)
        if conventions.status == "missing":
            # No config: run the built-in default trio (advisory) instead of
            # rendering a bare "no konpy.json" note.
            conventions = default_conventions(
                file_system, analyzed_paths=frozenset(collected.structures)
            )
        tool_lanes = tool_lanes_future.result()

    return ReportData(
        files=len(collected.structures),
        test_files=len(collected.test_paths),
        generated_files=len(collected.generated),
        vendor_files=len(collected.vendor_dropped),
        vendor_roots=collected.vendor.matched_roots,
        loc=collected.loc,
        skipped_unparsable=collected.skipped,
        unused=tuple(unused.diagnostics),
        literal_groups=literal_groups,
        function_groups=function_groups,
        tool_lanes=tool_lanes,
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
    "ReportToolLane",
    "assemble_report",
]
