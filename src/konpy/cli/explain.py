from __future__ import annotations

import sys
from enum import StrEnum

from konpy.config.cli_placeholders import normalize_placeholder_arg, parse_cli_placeholders
from konpy.config.errors import Err
from konpy.config.loader import load_config_runtime
from konpy.core.explain import render_explain


class ExplainFormat(StrEnum):
    """Output format for `konpy explain`: markdown or plain text."""

    MD = "md"
    TEXT = "text"


def run_explain_command(
    *,
    config_path: str | None,
    config_package: str | None,
    placeholder: list[str] | None,
    format: ExplainFormat | str = ExplainFormat.MD,
) -> int:
    """Run the `konpy explain` flow: load config and render agent guidance.

    Loads the resolved config and renders its active conventions/predicates
    as prevention-side guidance for a code-writing agent, writing the result
    to stdout.
    """
    cli_placeholders_result = parse_cli_placeholders(
        raw=normalize_placeholder_arg(placeholder),
    )
    if isinstance(cli_placeholders_result, Err):
        _write_error(cli_placeholders_result.error)
        return 1

    loaded_result = load_config_runtime(
        config_path=config_path,
        config_package=config_package,
        cli_placeholders=cli_placeholders_result.value,
    )
    if isinstance(loaded_result, Err):
        _write_error(loaded_result.error)
        return 1

    resolved_format = format.value if isinstance(format, ExplainFormat) else format
    rendered = render_explain(
        loaded_result.value.config,
        format=resolved_format,  # type: ignore[arg-type]
        predicate_registry=loaded_result.value.predicate_registry,
    )

    sys.stdout.write(rendered)
    sys.stdout.write("\n")
    return 0


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["ExplainFormat", "run_explain_command"]
