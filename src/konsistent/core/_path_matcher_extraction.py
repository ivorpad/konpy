from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from konsistent.core.constraints import (
    parse_placeholder_constraint,
    validate_placeholder_constraint,
)

_PLACEHOLDER_REGEX = re.compile(
    r"\{([a-zA-Z][a-zA-Z0-9]*)(?::([a-zA-Z][a-zA-Z0-9]*(?:\([^}]*\))?))?}"
)
_VALID_VALUE_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")
_GLOB_WILDCARD_REGEX = re.compile(r"[*?[\]]")


@dataclass(frozen=True, kw_only=True)
class _CollectedPlaceholder:
    name: str
    constraint_raw: str | None = None


@dataclass(frozen=True, kw_only=True)
class _ExtractedValues:
    values: dict[str, str]
    constraints: dict[str, str]


def has_placeholders(pattern: str) -> bool:
    """Return whether `pattern` contains a `{name}`-style placeholder segment."""
    return _PLACEHOLDER_REGEX.search(pattern) is not None


def pattern_to_glob(pattern: str) -> str:
    """Replace every `{name}` placeholder in `pattern` with a `*` glob wildcard."""
    return _PLACEHOLDER_REGEX.sub("*", pattern)


def _collect_placeholders(segment: str) -> list[_CollectedPlaceholder]:
    return [
        _CollectedPlaceholder(name=match.group(1), constraint_raw=match.group(2))
        for match in _PLACEHOLDER_REGEX.finditer(segment)
    ]


def _match_segment_as_glob(*, pattern_segment: str, path_segment: str) -> bool:
    regex_parts: list[str] = []

    for char in pattern_segment:
        if char == "*":
            regex_parts.append("[^/]*")
        elif char == "?":
            regex_parts.append("[^/]")
        else:
            regex_parts.append(re.escape(char))

    return re.fullmatch("".join(regex_parts), path_segment) is not None


def _extract_value_from_segment(
    *,
    pattern_segment: str,
    path_segment: str,
) -> _ExtractedValues | None:
    placeholders = _collect_placeholders(pattern_segment)

    if len(placeholders) == 0:
        if pattern_segment == path_segment:
            return _ExtractedValues(values={}, constraints={})
        if _GLOB_WILDCARD_REGEX.search(pattern_segment) is not None:
            if _match_segment_as_glob(
                pattern_segment=pattern_segment,
                path_segment=path_segment,
            ):
                return _ExtractedValues(values={}, constraints={})
            return None
        return None

    regex_parts: list[str] = []
    last_index = 0
    for match in _PLACEHOLDER_REGEX.finditer(pattern_segment):
        regex_parts.append(re.escape(pattern_segment[last_index : match.start()]))
        regex_parts.append("([a-zA-Z0-9_-]+)")
        last_index = match.end()
    regex_parts.append(re.escape(pattern_segment[last_index:]))

    segment_match = re.fullmatch("".join(regex_parts), path_segment)
    if segment_match is None:
        return None

    values: dict[str, str] = {}
    constraints: dict[str, str] = {}

    for index, placeholder in enumerate(placeholders):
        values[placeholder.name] = segment_match.group(index + 1)
        if placeholder.constraint_raw:
            constraints[placeholder.name] = placeholder.constraint_raw

    return _ExtractedValues(values=values, constraints=constraints)


def _satisfies_constraints(
    *,
    values: Mapping[str, str],
    constraints: Mapping[str, str],
) -> bool:
    for name, raw in constraints.items():
        constraint = parse_placeholder_constraint(raw)
        if constraint is not None and not validate_placeholder_constraint(values[name], constraint):
            return False
    return True


def _merge_extracted(
    *,
    existing: dict[str, str],
    incoming: Mapping[str, str],
) -> bool:
    for name, value in incoming.items():
        if _VALID_VALUE_REGEX.fullmatch(value) is None:
            return False
        if name in existing and existing[name] != value:
            return False
        existing[name] = value
    return True


def _try_extract_placeholders(
    *,
    pattern: str,
    path_segments: list[str],
) -> dict[str, str] | None:
    pattern_segments = pattern.split("/")
    if len(pattern_segments) != len(path_segments):
        return None

    extracted: dict[str, str] = {}
    all_constraints: dict[str, str] = {}

    for index, pattern_segment in enumerate(pattern_segments):
        segment_result = _extract_value_from_segment(
            pattern_segment=pattern_segment,
            path_segment=path_segments[index],
        )
        if segment_result is None:
            return None
        if not _merge_extracted(existing=extracted, incoming=segment_result.values):
            return None
        all_constraints.update(segment_result.constraints)

    if not _satisfies_constraints(values=extracted, constraints=all_constraints):
        return None

    return extracted


__all__ = ["has_placeholders", "pattern_to_glob"]
