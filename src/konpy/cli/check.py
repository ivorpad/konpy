from __future__ import annotations

import sys
from enum import Enum, StrEnum
from pathlib import Path

from konpy.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konpy.config.errors import Err
from konpy.config.loader import load_config_runtime
from konpy.config.schema import ConfigV1
from konpy.core.diff_scope import resolve_diff_scope
from konpy.core.filesystem import RealFileSystem
from konpy.core.reporters import (
    count_severities,
    format_default,
    format_github,
    format_json,
    format_markdown,
    resolve_format,
)
from konpy.core.runner import RunResult, run
from konpy.core.truncate import format_truncation_message, truncate_diagnostics


class OutputFormat(StrEnum):
    """The `--format` choices accepted by the `check` command."""

    DEFAULT = "default"
    JSON = "json"
    GITHUB = "github"
    MARKDOWN = "markdown"


class DiagnosticLevel(StrEnum):
    """The `--diagnostic-level` choices accepted by the `check` command."""

    WARNING = "warning"
    ERROR = "error"


def run_check_command(
    *,
    config_path: str | None,
    config_package: str | None,
    format: OutputFormat | str,
    verbose: bool,
    max_diagnostics: int,
    colors: bool | None,
    error_on_warnings: bool,
    diagnostic_level: DiagnosticLevel | str,
    placeholder: list[str] | None,
    show_suppressed: bool = False,
    files: list[str] | None = None,
    changed: bool = False,
) -> int:
    """Run `konpy check` and write the formatted report to stdout.

    Returns the process exit code: 1 on config/scope errors or violations at
    or above the failure threshold, 0 otherwise.
    """
    del verbose

    cli_placeholders_result = parse_cli_placeholders(
        raw=normalize_placeholder_arg(placeholder),
    )
    if isinstance(cli_placeholders_result, Err):
        _write_error(cli_placeholders_result.error)
        return 1

    scope_result = resolve_diff_scope(files=files, changed=changed, cwd=Path.cwd())
    if isinstance(scope_result, Err):
        _write_error(scope_result.error)
        return 1
    target_files = scope_result.value

    loaded_result = load_config_runtime(
        config_path=config_path,
        config_package=config_package,
        cli_placeholders=cli_placeholders_result.value,
    )
    if isinstance(loaded_result, Err):
        _write_error(loaded_result.error)
        return 1

    loaded = loaded_result.value
    diagnostic_level_value = _enum_value(diagnostic_level)
    config = _filter_config_for_diagnostic_level(
        config=loaded.config,
        diagnostic_level=diagnostic_level_value,
    )
    run_result = run(
        config=config,
        file_system=RealFileSystem(cwd=Path.cwd()),
        predicate_registry=loaded.predicate_registry,
        report_suppression_warnings=diagnostic_level_value != "error",
        target_files=target_files,
    )

    truncation = truncate_diagnostics(
        diagnostics=run_result.diagnostics,
        max=max_diagnostics,
    )
    reported_result = RunResult(
        diagnostics=truncation.diagnostics,
        files_checked=run_result.files_checked,
        duration_ms=run_result.duration_ms,
        suppressed_diagnostics=run_result.suppressed_diagnostics,
    )

    total_errors, total_warnings = count_severities(run_result.diagnostics)

    resolved_format = resolve_format(format=_enum_value(format))
    formatted = _format_result(
        result=reported_result,
        format=resolved_format,
        colors=colors,
        show_suppressed=show_suppressed,
        total_errors=total_errors,
        total_warnings=total_warnings,
        omitted=truncation.omitted,
    )

    output: list[str] = []
    if formatted:
        output.append(formatted)
    # `--format json` must stay a single parseable JSON object on stdout
    # (product invariant: JSON output is always {diagnostics, suppressed,
    # summary, truncation}). `summary.errors`/`summary.warnings` are always
    # the full pre-truncation totals, and `truncation: {shown, omitted}` is
    # always present, so a low `--max-diagnostics` never silently hides how
    # much was cut (see docs/guides/agent-eval.md). The human-readable "...
    # and N more" notice is plain text, not JSON, so it is only appended for
    # non-JSON formats -- the `diagnostics` array itself stays truncated to
    # `--max-diagnostics` in both cases; that cap is the point of the flag.
    if truncation.omitted > 0 and resolved_format != "json":
        output.append(format_truncation_message(truncation.omitted))
    if output:
        sys.stdout.write("\n".join(output))
        sys.stdout.write("\n")

    if _has_errors(run_result):
        return 1
    if error_on_warnings and _has_warnings(run_result):
        return 1

    return 0


def _filter_config_for_diagnostic_level(
    *,
    config: ConfigV1,
    diagnostic_level: str,
) -> ConfigV1:
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


def _format_result(
    *,
    result: RunResult,
    format: str,
    colors: bool | None,
    show_suppressed: bool,
    total_errors: int | None = None,
    total_warnings: int | None = None,
    omitted: int = 0,
) -> str:
    if format == "json":
        return format_json(
            result,
            show_suppressed=show_suppressed,
            total_errors=total_errors,
            total_warnings=total_warnings,
            omitted=omitted,
        )
    if format == "github":
        return format_github(result, show_suppressed=show_suppressed)
    if format == "markdown":
        return format_markdown(result, show_suppressed=show_suppressed)
    return format_default(result, colors=colors, show_suppressed=show_suppressed)


def _has_errors(result: RunResult) -> bool:
    return any(diagnostic.severity == "error" for diagnostic in result.diagnostics)


def _has_warnings(result: RunResult) -> bool:
    return any(diagnostic.severity == "warning" for diagnostic in result.diagnostics)


def _enum_value(value: Enum | str) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return value


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["DiagnosticLevel", "OutputFormat", "run_check_command"]
