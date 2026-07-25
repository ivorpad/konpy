"""Result types and validation-error formatting for the config pipeline.
The pipeline returns Ok/Err instead of raising (mirrors the upstream
discriminated-union results), and pydantic errors are rendered zod-style as
two-space-indented "  - path: message" lines.
"""

import re
from dataclasses import dataclass

from pydantic import ValidationError


@dataclass(frozen=True)
class Ok[T]:
    """A successful Result, wrapping the produced value."""

    value: T


@dataclass(frozen=True)
class Err:
    """A failed Result, wrapping a human-readable error message."""

    error: str


type Result[T] = Ok[T] | Err

_TYPE_TAG_NAMES = {
    "str",
    "int",
    "bool",
    "float",
    "list",
    "dict",
    "constrained-str",
    "function-after",
    "union",
    "json-or-python",
}

_ALIAS_FIELDS = {"if_": "if", "for_": "for", "from_": "from", "import_": "import"}


def _is_union_tag(part: str) -> bool:
    if part in _TYPE_TAG_NAMES:
        return True
    if "[" in part or "(" in part:
        return True
    # Model-class union tags are PascalCase; config field names and map keys
    # are lowercase-first (enforced by the schema regexes).
    return part[:1].isupper() and part.isascii() and re.match(r"^[A-Za-z0-9_]+$", part) is not None


def format_error_path(loc: tuple[str | int, ...]) -> str:
    """Render a pydantic error location tuple as a dotted path, dropping union-tag segments."""
    parts: list[str] = []
    for raw_part in loc:
        if isinstance(raw_part, int):
            parts.append(str(raw_part))
            continue
        part = _ALIAS_FIELDS.get(raw_part, raw_part)
        if _is_union_tag(part):
            continue
        parts.append(part)
    return ".".join(parts)


def format_validation_error(error: ValidationError) -> str:
    """Render a pydantic ValidationError as deduplicated zod-style "  - path: message" lines."""
    lines: list[str] = []
    seen: set[str] = set()
    for issue in error.errors():
        path = format_error_path(tuple(issue["loc"]))
        message = issue["msg"]
        if path == "version" and message == "Field required":
            message = 'Field required (expected "v1")'
        line = f"  - {path}: {message}"
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)
