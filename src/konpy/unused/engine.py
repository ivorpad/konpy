"""Engine wiring for unused-code detection.

Resolves an :class:`UnusedCodeV1` (applying engine-level defaults and merging
framework presets), globs the relevant files through the :class:`FileSystem`,
builds the reference index, collects definitions from production files, and
emits diagnostics for the ``dead`` and ``test-only`` verdicts.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass

from konpy.config.schema import UnusedCodeV1
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.core.filesystem import FileSystem
from konpy.unused.classifier import Classification, ResolvedUnusedConfig, classify
from konpy.unused.definitions import collect_definitions
from konpy.unused.presets import (
    DATACLASS_DECORATOR_PRESETS,
    HOOK_NAME_PRESETS,
    MODEL_BASE_PRESETS,
    REGISTRY_DECORATOR_PRESETS,
)
from konpy.unused.references import PythonRefSource, build_reference_index

DEFAULT_INCLUDE: tuple[str, ...] = ("**/*.py",)
DEFAULT_TEST_GLOBS: tuple[str, ...] = (
    "tests/**",
    "test_*.py",
    "*_test.py",
    "conftest.py",
)
DEFAULT_ENTRYPOINT_FILES: tuple[str, ...] = (
    "Dockerfile*",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "template*.yml",
    "template*.yaml",
    "serverless*.yml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
)
DEFAULT_SEVERITY: DiagnosticSeverity = "warning"

CONVENTION_NAME = "unused-code"


@dataclass(frozen=True, kw_only=True)
class UnusedRunResult:
    """Diagnostics from an unused-code run plus the production files scanned."""

    diagnostics: list[Diagnostic]
    files_scanned: set[str]


def resolve_config(config: UnusedCodeV1) -> ResolvedUnusedConfig:
    """Merge `config` with engine defaults and framework presets."""
    return ResolvedUnusedConfig(
        include=tuple(config.include) if config.include else DEFAULT_INCLUDE,
        test_globs=tuple(config.testGlobs) if config.testGlobs else DEFAULT_TEST_GLOBS,
        entrypoint_files=(
            tuple(config.entrypointFiles) if config.entrypointFiles else DEFAULT_ENTRYPOINT_FILES
        ),
        registry_decorators=REGISTRY_DECORATOR_PRESETS + tuple(config.registryDecorators or ()),
        hook_names=HOOK_NAME_PRESETS | frozenset(config.hookNames or ()),
        model_bases=MODEL_BASE_PRESETS | frozenset(config.modelBases or ()),
        # A user may list a dataclass decorator under ``modelBases`` (per the
        # plan's config sketch), so those entries extend both sets.
        dataclass_decorators=DATACLASS_DECORATOR_PRESETS | frozenset(config.modelBases or ()),
        allow=frozenset(config.allow or ()),
        severity=config.severity or DEFAULT_SEVERITY,
    )


def run_unused_code(*, config: UnusedCodeV1, file_system: FileSystem) -> list[Diagnostic]:
    """Run unused-code detection and return just its diagnostics."""
    return run_unused_code_with_metadata(
        config=config,
        file_system=file_system,
    ).diagnostics


def run_unused_code_with_metadata(
    *,
    config: UnusedCodeV1,
    file_system: FileSystem,
    source_cache: dict[str, str] | None = None,
) -> UnusedRunResult:
    """Run unused-code detection, returning diagnostics plus scanned production files."""
    resolved = resolve_config(config)

    test_files = set(_python_files(file_system, resolved.test_globs))
    include_files = _python_files(file_system, resolved.include)
    prod_files = [path for path in include_files if path not in test_files]
    # Test-glob files feed the reference index only -- they can never carry
    # an unused-code diagnostic, so they are excluded from `files_scanned`
    # (which drives suppression-hygiene candidacy in the runner).
    reference_sources = set(prod_files) | test_files

    python_sources: list[PythonRefSource] = []
    prod_trees: dict[str, ast.Module] = {}

    for path in sorted(reference_sources):
        tree = _parse(file_system, path, source_cache=source_cache)
        if tree is None:
            continue
        is_test = path in test_files
        python_sources.append(
            PythonRefSource(module_path=path, tree=tree, is_test=is_test)
        )
        if not is_test:
            prod_trees[path] = tree

    entrypoint_texts = _entrypoint_texts(
        file_system,
        resolved.entrypoint_files,
        source_cache=source_cache,
    )
    index = build_reference_index(
        python_sources=python_sources,
        entrypoint_texts=entrypoint_texts,
    )

    diagnostics: list[Diagnostic] = []
    for path in sorted(prod_trees):
        for definition in collect_definitions(module=prod_trees[path], module_path=path):
            classification = classify(definition=definition, index=index, config=resolved)
            diagnostic = _diagnostic_for(classification, resolved.severity)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    diagnostics.sort(key=lambda d: (d.file_path, d.line or 0, d.column or 0))
    return UnusedRunResult(
        diagnostics=diagnostics,
        files_scanned=set(prod_files),
    )


def _python_files(file_system: FileSystem, patterns: Sequence[str]) -> list[str]:
    if not patterns:
        return []
    results: list[str] = []
    for path in file_system.glob(list(patterns)):
        if path.endswith(".py") and not file_system.is_directory(path):
            results.append(path)
    return results


def _entrypoint_texts(
    file_system: FileSystem,
    patterns: Sequence[str],
    *,
    source_cache: dict[str, str] | None = None,
) -> list[str]:
    if not patterns:
        return []
    texts: list[str] = []
    for path in sorted(set(file_system.glob(list(patterns)))):
        if file_system.is_directory(path):
            continue
        try:
            texts.append(_read_source(file_system, path, source_cache=source_cache))
        except OSError:
            continue
    return texts


def _parse(
    file_system: FileSystem,
    path: str,
    *,
    source_cache: dict[str, str] | None = None,
) -> ast.Module | None:
    try:
        source = _read_source(file_system, path, source_cache=source_cache)
    except OSError:
        return None
    try:
        return ast.parse(source, filename=path)
    except SyntaxError:
        return None


def _read_source(
    file_system: FileSystem,
    path: str,
    *,
    source_cache: dict[str, str] | None,
) -> str:
    if source_cache is None:
        return file_system.read_file(path)

    cached = source_cache.get(path)
    if cached is not None:
        return cached

    source = file_system.read_file(path)
    source_cache[path] = source
    return source


def _diagnostic_for(
    classification: Classification,
    severity: DiagnosticSeverity,
) -> Diagnostic | None:
    definition = classification.definition

    if classification.verdict == "dead":
        return create_diagnostic(
            file_path=definition.module_path,
            predicate_name="unusedCode.dead",
            message=f'Unused definition "{definition.qualname}" is never referenced',
            convention_name=CONVENTION_NAME,
            line=definition.lineno,
            column=definition.col,
            severity=severity,
        )

    if classification.verdict == "test-only":
        return create_diagnostic(
            file_path=definition.module_path,
            predicate_name="unusedCode.testOnly",
            message=f'Definition "{definition.qualname}" is only referenced by tests',
            convention_name=CONVENTION_NAME,
            line=definition.lineno,
            column=definition.col,
            severity=severity,
        )

    return None


__all__ = [
    "CONVENTION_NAME",
    "DEFAULT_ENTRYPOINT_FILES",
    "DEFAULT_INCLUDE",
    "DEFAULT_SEVERITY",
    "DEFAULT_TEST_GLOBS",
    "UnusedRunResult",
    "resolve_config",
    "run_unused_code",
    "run_unused_code_with_metadata",
]
