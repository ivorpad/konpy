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
from konpy.unused._engine_files import (
    _entrypoint_texts,
    _local_module_roots,
    _parse,
    _python_files,
)
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
# Recursive (`**/` matches zero directories, so root-level files still match):
# repos keep tests in nested dirs (e2e-tests/, pkg/tests/) and ship console
# scripts from nested pyproject.toml files (examples/*/pyproject.toml).
DEFAULT_TEST_GLOBS: tuple[str, ...] = (
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/conftest.py",
)
DEFAULT_ENTRYPOINT_FILES: tuple[str, ...] = (
    "**/Dockerfile*",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/template*.yml",
    "**/template*.yaml",
    "**/serverless*.yml",
    "**/pyproject.toml",
    "**/setup.py",
    "**/setup.cfg",
    "**/Makefile",
)
DEFAULT_SEVERITY: DiagnosticSeverity = "warning"
# Vendored/build trees are never scanned and never feed references: a stale
# copy of production code (or a dependency's setup.py whose text happens to
# contain a matching token) would otherwise silently mask real dead code.
# Dot-directories (.venv, .git) are already skipped by GLOBSTAR-without-
# DOTGLOB; these are the non-dot equivalents.
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "**/node_modules/**",
    "**/venv/**",
    "**/build/**",
    "**/dist/**",
    "**/__pycache__/**",
    "**/*.egg-info/**",
    "**/site-packages/**",
)

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
    exclude: Sequence[str] | None = None,
    reference_only: Sequence[str] | None = None,
) -> UnusedRunResult:
    """Run unused-code detection, returning diagnostics plus scanned production files.

    `exclude` glob patterns (additive, caller-supplied) remove matching paths
    from the include, test, and entrypoint sets on top of the always-applied
    `DEFAULT_EXCLUDE` vendored/build globs. `reference_only` paths (e.g. the
    report's generator-banner files) feed the reference index as production
    references but never carry diagnostics themselves — unlike excludes, so
    hand-written code referenced only from generated code stays used.
    """
    resolved = resolve_config(config)
    # Dedupe so a caller passing DEFAULT_EXCLUDE back reuses the file
    # system's cached glob for the identical pattern set instead of paying a
    # second full-tree walk.
    exclude_patterns = list(dict.fromkeys((*DEFAULT_EXCLUDE, *(exclude or ()))))
    excluded = set(file_system.glob(exclude_patterns))

    test_files = set(_python_files(file_system, resolved.test_globs)) - excluded
    reference_only_files = (set(reference_only or ()) - excluded) - test_files
    include_files = [
        path for path in _python_files(file_system, resolved.include) if path not in excluded
    ]
    prod_files = [
        path
        for path in include_files
        if path not in test_files and path not in reference_only_files
    ]
    # Test-glob and reference-only files feed the reference index only -- they
    # can never carry an unused-code diagnostic, so they are excluded from
    # `files_scanned` (which drives suppression-hygiene candidacy in the
    # runner).
    reference_sources = set(prod_files) | test_files | reference_only_files

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
        if not is_test and path not in reference_only_files:
            prod_trees[path] = tree

    entrypoint_texts = _entrypoint_texts(
        file_system,
        resolved.entrypoint_files,
        source_cache=source_cache,
        excluded=excluded,
    )
    index = build_reference_index(
        python_sources=python_sources,
        entrypoint_texts=entrypoint_texts,
    )
    local_roots = _local_module_roots(reference_sources)

    diagnostics: list[Diagnostic] = []
    for path in sorted(prod_trees):
        for definition in collect_definitions(module=prod_trees[path], module_path=path):
            classification = classify(
                definition=definition,
                index=index,
                config=resolved,
                local_module_roots=local_roots,
            )
            diagnostic = _diagnostic_for(classification, resolved.severity)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

    diagnostics.sort(key=lambda d: (d.file_path, d.line or 0, d.column or 0))
    return UnusedRunResult(
        diagnostics=diagnostics,
        files_scanned=set(prod_files),
    )


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
    "DEFAULT_EXCLUDE",
    "DEFAULT_INCLUDE",
    "DEFAULT_SEVERITY",
    "DEFAULT_TEST_GLOBS",
    "UnusedRunResult",
    "resolve_config",
    "run_unused_code",
    "run_unused_code_with_metadata",
]
