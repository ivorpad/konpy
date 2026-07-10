from __future__ import annotations

from fnmatch import fnmatchcase


def _escape_fnmatch_pattern_except_star(pattern: str) -> str:
    parts: list[str] = []
    for char in pattern:
        if char == "*":
            parts.append("*")
        elif char == "[":
            parts.append("[[]")
        elif char == "]":
            parts.append("[]]")
        elif char == "?":
            parts.append("[?]")
        else:
            parts.append(char)
    return "".join(parts)


def _matches_pattern(value: str, pattern: str) -> bool:
    return fnmatchcase(value, _escape_fnmatch_pattern_except_star(pattern))


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(_matches_pattern(value, pattern) for pattern in patterns)


__all__: list[str] = []
