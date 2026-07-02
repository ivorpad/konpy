from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from konsistent.config.errors import Err, Ok, Result
from konsistent.config.schema import PLACEHOLDER_NAME_PATTERN, PLACEHOLDER_VALUE_PATTERN

_NAME_REGEX = re.compile(f"^{PLACEHOLDER_NAME_PATTERN}$")
_VALUE_REGEX = re.compile(f"^{PLACEHOLDER_VALUE_PATTERN}$")


def parse_cli_placeholders(*, raw: Sequence[str]) -> Result[dict[str, str]]:
    placeholders: dict[str, str] = {}

    for entry in raw:
        colon = entry.find(":")
        if colon < 1 or colon == len(entry) - 1:
            return Err(f'Invalid --placeholder "{entry}". Expected format "name:value".')

        name = entry[:colon]
        value = entry[colon + 1 :]

        if _NAME_REGEX.fullmatch(name) is None:
            return Err(
                f'Invalid --placeholder "{entry}": name "{name}" must match '
                "[a-zA-Z][a-zA-Z0-9]*."
            )

        if _VALUE_REGEX.fullmatch(value) is None:
            return Err(
                f'Invalid --placeholder "{entry}": value "{value}" must match '
                "[a-zA-Z0-9_-]+."
            )

        placeholders[name] = value

    return Ok(placeholders)


def normalize_placeholder_arg(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list | tuple):
        return [item for item in raw if isinstance(item, str)]
    return []


__all__ = ["normalize_placeholder_arg", "parse_cli_placeholders"]
