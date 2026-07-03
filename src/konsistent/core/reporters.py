from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from konsistent.core._reporters_default import format_default
from konsistent.core._reporters_github import format_github
from konsistent.core._reporters_json import format_json
from konsistent.core._reporters_markdown import format_markdown
from konsistent.core._reporters_shared import count_severities

ReporterFormat = Literal["default", "json", "github", "markdown"]


def resolve_format(
    *,
    format: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the ``default`` format to ``github`` when running in GitHub Actions."""
    if format != "default":
        return format

    environment = os.environ if env is None else env
    if environment.get("GITHUB_ACTIONS") == "true":
        return "github"

    return "default"


__all__ = [
    "ReporterFormat",
    "count_severities",
    "format_default",
    "format_github",
    "format_json",
    "format_markdown",
    "resolve_format",
]
