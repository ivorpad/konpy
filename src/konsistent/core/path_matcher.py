from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from konsistent.core._path_matcher_extraction import (
    _try_extract_placeholders,
    has_placeholders,
    pattern_to_glob,
)
from konsistent.core.filesystem import FileSystem
from konsistent.core.placeholders import PlaceholderValue

_TEMPLATE_IN_PATH_REGEX = re.compile(r"\$\{([a-zA-Z][a-zA-Z0-9]*)\}")


@dataclass(frozen=True, kw_only=True)
class MatchedPath:
    """A filesystem path matched against a (possibly placeholder-bearing) pattern."""

    path: str
    placeholders: dict[str, PlaceholderValue]


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
    """Resolve glob/placeholder `patterns` against `file_system` into matched paths.

    Patterns prefixed with `!` are negative: paths (or their descendants)
    that they match are excluded from the positive-pattern results.
    """
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
