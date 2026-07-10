"""Shared config/runtime helpers for commands that run deterministic checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from konpy.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konpy.config.errors import Err, Ok, Result
from konpy.config.loader import load_config_runtime
from konpy.config.schema import ConfigV1
from konpy.core.runner import RunResult
from konpy.predicates.registry import PredicateRegistry

__all__ = [
    "PreparedCheckRuntime",
    "enum_value",
    "filter_config_for_diagnostic_level",
    "has_errors",
    "has_warnings",
    "prepare_check_runtime",
]


@dataclass(frozen=True, kw_only=True)
class PreparedCheckRuntime:
    """A loaded, diagnostic-level-filtered config plus its predicate registry."""

    config: ConfigV1
    predicate_registry: PredicateRegistry
    diagnostic_level_value: str


def prepare_check_runtime(
    *,
    config_path: str | None,
    config_package: str | None,
    diagnostic_level: Enum | str,
    placeholder: list[str] | None,
) -> Result[PreparedCheckRuntime]:
    """Load config with the same placeholder/filter semantics as `konpy check`."""
    cli_placeholders_result = parse_cli_placeholders(
        raw=normalize_placeholder_arg(placeholder),
    )
    if isinstance(cli_placeholders_result, Err):
        return cli_placeholders_result

    loaded_result = load_config_runtime(
        config_path=config_path,
        config_package=config_package,
        cli_placeholders=cli_placeholders_result.value,
    )
    if isinstance(loaded_result, Err):
        return loaded_result

    diagnostic_level_value = enum_value(diagnostic_level)
    config = filter_config_for_diagnostic_level(
        config=loaded_result.value.config,
        diagnostic_level=diagnostic_level_value,
    )

    return Ok(
        PreparedCheckRuntime(
            config=config,
            predicate_registry=loaded_result.value.predicate_registry,
            diagnostic_level_value=diagnostic_level_value,
        )
    )


def filter_config_for_diagnostic_level(
    *,
    config: ConfigV1,
    diagnostic_level: str,
) -> ConfigV1:
    """Drop warning-level checks when `--diagnostic-level error` is active."""
    if diagnostic_level != "error":
        return config

    update: dict[str, object] = {
        "conventions": [
            convention
            for convention in config.conventions
            if (convention.severity or "error") != "warning"
        ]
    }

    if config.unusedCode is not None and (config.unusedCode.severity or "warning") == "warning":
        update["unusedCode"] = None

    return config.model_copy(update=update)


def has_errors(result: RunResult) -> bool:
    """Return whether a run result has any unsuppressed error diagnostics."""
    return any(diagnostic.severity == "error" for diagnostic in result.diagnostics)


def has_warnings(result: RunResult) -> bool:
    """Return whether a run result has any unsuppressed warning diagnostics."""
    return any(diagnostic.severity == "warning" for diagnostic in result.diagnostics)


def enum_value(value: Enum | str) -> str:
    """Normalize a Typer enum or raw string option value."""
    if isinstance(value, Enum):
        return str(value.value)
    return value
