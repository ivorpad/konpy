"""Low-level regexes and helpers shared by the placeholder-usage collectors.

Split out of placeholder_validator.py to keep every module in this split
small; these primitives have no dependency on the collector modules built
on top of them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

USAGE_REGEX = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9]*)")
DECLARATION_REGEX = re.compile(
    r"\{([a-zA-Z][a-zA-Z0-9]*)(?::[a-zA-Z][a-zA-Z0-9]*(?:\([^}]*\))?)?\}"
)


class _Usage:
    def __init__(self, *, name: str, key: str) -> None:
        self.name = name
        self.key = key


def _collect_declarations(paths: str | Sequence[str]) -> set[str]:
    declared: set[str] = set()
    entries = [paths] if isinstance(paths, str) else paths
    for entry in entries:
        _add_declarations_from_string(value=entry, into=declared)
    return declared


def _add_declarations_from_string(*, value: str, into: set[str]) -> None:
    for match in DECLARATION_REGEX.finditer(value):
        into.add(match.group(1))


def _push_string_usages(
    *,
    value: object,
    key: str,
    declared: set[str],
    usages: list[_Usage],
) -> None:
    if not isinstance(value, str):
        return
    for match in USAGE_REGEX.finditer(value):
        name = match.group(1)
        if name not in declared:
            usages.append(_Usage(name=name, key=key))


def _to_alias_dict(value: object) -> dict[str, object]:
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected mapping-like value, got {type(value).__name__}")


__all__: list[str] = []
