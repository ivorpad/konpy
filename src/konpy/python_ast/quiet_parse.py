"""Warning-free `ast.parse` for analyzed source.

konpy parses code it does not own. CPython emits `SyntaxWarning` (and
occasionally `DeprecationWarning`) at *parse* time for things like an invalid
escape sequence, so analyzing a repository that vendors third-party or generated
code printed raw interpreter warnings interleaved with konpy's own report — text
konpy never authored, about files the caller may have deliberately excluded.

konpy already reports parse problems its own way (`SyntaxError` handling per
lane, plus the report's "N unreadable/unparsable files skipped" note), so the
interpreter's parse-time warnings are pure noise. Suppression is scoped to the
single `ast.parse` call, so warnings raised by konpy's own code still surface.
"""

from __future__ import annotations

import ast
import warnings

__all__ = ["quiet_parse"]


def quiet_parse(
    source: str,
    *,
    filename: str = "<unknown>",
    type_comments: bool = False,
) -> ast.Module:
    """Parse `source` without letting parse-time warnings reach stderr.

    Raises whatever `ast.parse` raises (notably `SyntaxError`, and `ValueError`
    for source containing null bytes); callers keep their own handling.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(source, filename=filename, type_comments=type_comments)
