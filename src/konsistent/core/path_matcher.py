from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from konsistent.core.constraints import (
    parse_placeholder_constraint,
    validate_placeholder_constraint,
)
from konsistent.core.filesystem import FileSystem
from konsistent.core.placeholders import PlaceholderValue

_PLACEHOLDER_REGEX = re.compile(
    r"\{([a-zA-Z][a-zA-Z0-9]*)(?::([a-zA-Z][a-zA-Z0-9]*(?:\([^}]*\))?))?}"
)
_TEMPLATE_IN_PATH_REGEX = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9]*)\}")
_VALID_VALUE_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")
_GLOB_WILDCARD_REGEX = re.compile(r"[*?[\]]")


@dataclass(frozen=True, kw_only=True)
class MatchedPath:
    path: str
    placeholders: dict[str, PlaceholderValue]


@dataclass(frozen=True, kw_only=True)
class _CollectedPlaceholder:
    name: str
    constraint_raw: str | None = None


@dataclass(frozen=True, kw_only=True)
class _ExtractedValues:
    values: dict[str, str]
    constraints: dict[str, str]


def has_placeholders(pattern: str) -> bool:
    return _PLACEHOLDER_REGEX.search(pattern) is not None


def pattern_to_glob(pattern: str) -> str:
    return _PLACEHOLDER_REGEX.sub("*", pattern)


def match_paths(
    *,
    patterns: Sequence[str],
    file_system: FileSystem,
    kebab_to_pascal_map: dict[str, str] | None = None,
    kebab_to_camel_map: dict[str, str] | None = None,
    pascal_to_kebab_map: dict[str, str] | None = None,
    camel_to_kebab_map: dict[str, str] | None = None,
    camel_to_pascal_map: dict[str, str] | None = None,
    pascal_to_camel_map: dict[str, str] | None = None,
) -> list[MatchedPath]:
    positive_patterns: list[str] = []
    negative_patterns: list[str] = []

    for pattern in patterns:
        normalized = _normalize_templates_in_path(pattern)
        if normalized.startswith("!"):
            negative_patterns.append(normalized[1:])
        else:
            positive_patterns.append(normalized)

    positive_results = _resolve_positive_patterns(
        patterns=positive_patterns,
        file_system=file_system,
        kebab_to_pascal_map=kebab_to_pascal_map,
        kebab_to_camel_map=kebab_to_camel_map,
        pascal_to_kebab_map=pascal_to_kebab_map,
        camel_to_kebab_map=camel_to_kebab_map,
        camel_to_pascal_map=camel_to_pascal_map,
        pascal_to_camel_map=pascal_to_camel_map,
    )

    if not negative_patterns:
        return positive_results

    negative_globs = [pattern_to_glob(pattern) for pattern in negative_patterns]
    exclude_paths = [_strip_trailing_slash(path) for path in file_system.glob(negative_globs)]

    return [
        result
        for result in positive_results
        if not any(
            result.path == excluded_path or result.path.startswith(f"{excluded_path}/")
            for excluded_path in exclude_paths
        )
    ]


def _normalize_templates_in_path(pattern: str) -> str:
    return _TEMPLATE_IN_PATH_REGEX.sub(r"{\1}", pattern)


def _strip_trailing_slash(path: str) -> str:
    if path.endswith("/"):
        return path[:-1]
    return path


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
    path_segments: Sequence[str],
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


def _to_placeholder_map(
    *,
    raw: Mapping[str, str],
    kebab_to_pascal_map: dict[str, str] | None = None,
    kebab_to_camel_map: dict[str, str] | None = None,
    pascal_to_kebab_map: dict[str, str] | None = None,
    camel_to_kebab_map: dict[str, str] | None = None,
    camel_to_pascal_map: dict[str, str] | None = None,
    pascal_to_camel_map: dict[str, str] | None = None,
) -> dict[str, PlaceholderValue]:
    return {
        name: PlaceholderValue(
            value,
            kebab_to_pascal_map=kebab_to_pascal_map,
            kebab_to_camel_map=kebab_to_camel_map,
            pascal_to_kebab_map=pascal_to_kebab_map,
            camel_to_kebab_map=camel_to_kebab_map,
            camel_to_pascal_map=camel_to_pascal_map,
            pascal_to_camel_map=pascal_to_camel_map,
        )
        for name, value in raw.items()
    }


def _resolve_positive_patterns(
    *,
    patterns: Sequence[str],
    file_system: FileSystem,
    kebab_to_pascal_map: dict[str, str] | None = None,
    kebab_to_camel_map: dict[str, str] | None = None,
    pascal_to_kebab_map: dict[str, str] | None = None,
    camel_to_kebab_map: dict[str, str] | None = None,
    camel_to_pascal_map: dict[str, str] | None = None,
    pascal_to_camel_map: dict[str, str] | None = None,
) -> list[MatchedPath]:
    if not patterns:
        return []

    any_placeholders = any(has_placeholders(pattern) for pattern in patterns)
    if not any_placeholders:
        return [
            MatchedPath(path=_strip_trailing_slash(path), placeholders={})
            for path in file_system.glob(patterns)
        ]

    glob_patterns = [pattern_to_glob(pattern) for pattern in patterns]
    matched_paths = file_system.glob(glob_patterns)
    results: list[MatchedPath] = []

    for raw_path in matched_paths:
        matched_path = _strip_trailing_slash(raw_path)
        path_segments = matched_path.split("/")

        for pattern in patterns:
            if not has_placeholders(pattern):
                continue

            extracted = _try_extract_placeholders(
                pattern=pattern,
                path_segments=path_segments,
            )
            if extracted is None:
                continue

            results.append(
                MatchedPath(
                    path=matched_path,
                    placeholders=_to_placeholder_map(
                        raw=extracted,
                        kebab_to_pascal_map=kebab_to_pascal_map,
                        kebab_to_camel_map=kebab_to_camel_map,
                        pascal_to_kebab_map=pascal_to_kebab_map,
                        camel_to_kebab_map=camel_to_kebab_map,
                        camel_to_pascal_map=camel_to_pascal_map,
                        pascal_to_camel_map=pascal_to_camel_map,
                    ),
                )
            )
            break

    return results


__all__ = ["MatchedPath", "has_placeholders", "match_paths", "pattern_to_glob"]
