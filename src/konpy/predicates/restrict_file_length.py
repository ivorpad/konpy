"""`restrictFileLength` predicate: cap a file's physical line count.

Replaces the `matchContent` regex hack (`\\A(?:[^\\n]*\\n){301}`) with a real
predicate that names the actual line count and the limit in its diagnostic.
Content-based, so it works on any text file the convention's paths match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from konpy.core.context import PredicateContext
from konpy.core.count_lines import count_physical_lines
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konpy.core.filesystem import FileSystem

if TYPE_CHECKING:
    from konpy.config.schema import RestrictFileLengthOptionsV1

DEFAULT_MAX_LINES = 300
_FIX_HINT = (
    "Split this file into smaller single-purpose modules behind the same "
    "import surface."
)


def _get_value(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _max_lines(expected: Literal[True] | RestrictFileLengthOptionsV1) -> int:
    if expected is True:
        return DEFAULT_MAX_LINES
    value = _get_value(expected, "maxLines")
    return DEFAULT_MAX_LINES if value is None else int(value)


def check_restrict_file_length(
    *,
    expected: Literal[True] | RestrictFileLengthOptionsV1,
    context: PredicateContext,
    file_system: FileSystem,
    convention_name: str | None = None,
    severity: DiagnosticSeverity | None = None,
) -> list[Diagnostic]:
    """Flag files whose physical line count exceeds ``maxLines``."""
    max_lines = _max_lines(expected)

    try:
        content = file_system.read_file(context.path)
    except (OSError, UnicodeDecodeError):
        return []

    lines = count_physical_lines(content)
    if lines <= max_lines:
        return []

    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="restrictFileLength",
            message=f"File has {lines} lines (max {max_lines})",
            convention_name=convention_name,
            line=max_lines + 1,
            column=1,
            severity=severity,
            expected=f"at most {max_lines} lines",
            found=f"{lines} lines",
            fix_hint=_FIX_HINT,
        )
    ]


__all__ = ["DEFAULT_MAX_LINES", "check_restrict_file_length"]
