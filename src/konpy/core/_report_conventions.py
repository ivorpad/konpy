"""Conventions lanes for the zero-config report.

Two producers of `ReportConventions`: the configured lane runs `konpy.json`
when one exists, and the default lane runs a built-in, layout-agnostic rule
trio when none does -- barrel `__init__.py` files, no `typing.Any`, modules
at most 300 lines (tests exempt). Default findings are warning-severity and
advisory: they never change the report's exit code. `konpy init` writes the
full strict starter these defaults are drawn from.
"""

from __future__ import annotations

from pathlib import Path

from konpy.config.errors import Err
from konpy.config.loader import load_config_runtime
from konpy.config.schema import ConfigV1
from konpy.core._report_duplication import _EXAMPLE_SEGMENTS
from konpy.core._report_model import ReportConventions
from konpy.core.filesystem import FileSystem
from konpy.core.runner import run
from konpy.predicates.registry import builtin_predicate_registry
from konpy.unused.engine import DEFAULT_EXCLUDE, DEFAULT_TEST_GLOBS

_EXCLUDE_NEGATIONS = tuple(f"!{glob}" for glob in DEFAULT_EXCLUDE)
_TEST_NEGATIONS = tuple(f"!{glob}" for glob in DEFAULT_TEST_GLOBS)
# Example/tutorial trees simplify and repeat by design (the duplication lane
# *labels* them; a default rule shouldn't flag them at all).
_EXAMPLE_NEGATIONS = tuple(f"!**/{segment}/**" for segment in sorted(_EXAMPLE_SEGMENTS))

# Summary of the default trio rendered above the findings; single-sourced
# here so the renderer can never drift from what actually runs.
DEFAULT_CONVENTIONS_SUMMARY = (
    "barrel __init__ files, no typing.Any, modules ≤300 lines (tests/examples exempt)"
)


def _default_config_data() -> dict[str, object]:
    """The built-in default conventions, mirroring the `konpy init` starter.

    Only the layout-agnostic subset qualifies: rules assuming a `src/`
    layout, import style, or a CLI package location would false-fire on
    arbitrary repos. Everything is warning severity by design.
    """
    module_paths = ["**/*.py", *_TEST_NEGATIONS, *_EXAMPLE_NEGATIONS, *_EXCLUDE_NEGATIONS]
    return {
        "version": "v1",
        "conventions": [
            {
                "name": "init-files-are-barrels",
                "description": (
                    "Package __init__.py files never contain business logic; only "
                    "docstrings, imports, __all__, and re-export aliases."
                ),
                "hint": (
                    "Move non-barrel logic out of this __init__.py into a dedicated "
                    "module and re-export it here instead."
                ),
                "severity": "warning",
                "paths": ["**/__init__.py", *_EXAMPLE_NEGATIONS, *_EXCLUDE_NEGATIONS],
                "must": {"areBarrelFiles": True},
            },
            {
                "name": "no-typing-any",
                "description": "typing.Any defeats the type checker; annotate precisely.",
                "hint": (
                    "Replace Any with a precise type, a TypeVar, or object if the "
                    "value is genuinely opaque."
                ),
                "severity": "warning",
                "paths": module_paths,
                "mustNot": {"matchContent": [": Any\\b", "-> Any\\b", "\\[Any\\]"]},
            },
            {
                "name": "max-module-length",
                "description": "Modules longer than 300 lines should be split.",
                "hint": (
                    "Split this module into smaller single-purpose modules behind "
                    "the same import surface."
                ),
                "severity": "warning",
                "paths": module_paths,
                "must": {"restrictFileLength": {"maxLines": 300}},
            },
        ],
    }


def default_conventions(
    file_system: FileSystem, *, analyzed_paths: frozenset[str]
) -> ReportConventions:
    """Run the built-in defaults and keep findings on the report's own files.

    `analyzed_paths` is the report's post-exclusion file set, so vendored,
    generated, gitignored, and `--exclude`-matched files can never carry a
    default finding even though the conventions runner matched them.
    """
    registry = builtin_predicate_registry()
    config = ConfigV1.model_validate(
        _default_config_data(), context=registry.validation_context()
    )
    result = run(config=config, file_system=file_system, predicate_registry=registry)
    diagnostics = tuple(d for d in result.diagnostics if d.file_path in analyzed_paths)
    ordered = sorted(
        diagnostics,
        key=lambda d: (d.severity != "error", d.file_path, d.line or 0),
    )
    errors = sum(1 for d in diagnostics if d.severity == "error")
    return ReportConventions(
        status="defaults",
        files_checked=result.files_checked,
        errors=errors,
        warnings=len(diagnostics) - errors,
        top_diagnostics=tuple(ordered),
        error_text=None,
    )


def configured_conventions(file_system: FileSystem, config_path: Path) -> ReportConventions:
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


__all__ = [
    "DEFAULT_CONVENTIONS_SUMMARY",
    "configured_conventions",
    "default_conventions",
]
