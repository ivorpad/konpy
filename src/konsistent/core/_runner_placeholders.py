"""Placeholder resolution and `if`/`excludeFiles` gating for `run()`."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping

from konsistent.config.schema import MustBlockV1
from konsistent.core._runner_types import CaseMaps
from konsistent.core.constraints import (
    parse_placeholder_constraint,
    validate_placeholder_constraint,
)
from konsistent.core.context import PredicateContext
from konsistent.core.placeholders import PlaceholderValue


def _build_static_placeholders(
    *,
    raw: Mapping[str, str] | None,
    case_maps: CaseMaps,
) -> dict[str, PlaceholderValue]:
    if raw is None:
        return {}

    return {
        name: PlaceholderValue(
            value,
            kebab_to_pascal_map=case_maps["kebab_to_pascal_map"],
            kebab_to_camel_map=case_maps["kebab_to_camel_map"],
            pascal_to_kebab_map=case_maps["pascal_to_kebab_map"],
            camel_to_kebab_map=case_maps["camel_to_kebab_map"],
            camel_to_pascal_map=case_maps["camel_to_pascal_map"],
            pascal_to_camel_map=case_maps["pascal_to_camel_map"],
        )
        for name, value in raw.items()
    }


def _is_file_excluded(
    *,
    file_path: str,
    exclude_files: list[str] | None,
    context: PredicateContext,
) -> bool:
    if not exclude_files:
        return False

    for pattern in exclude_files:
        resolved = context.resolve_template(pattern)
        if file_path == resolved or posixpath.basename(file_path) == resolved:
            return True

    return False


def _evaluate_placeholder_satisfies(
    *,
    raw: str,
    context: PredicateContext,
) -> bool:
    colon_index = raw.find(":")
    if colon_index < 1:
        return False

    name = raw[:colon_index]
    constraint_raw = raw[colon_index + 1 :]
    placeholder = context.placeholders.get(name)
    if placeholder is None:
        return False

    constraint = parse_placeholder_constraint(constraint_raw)
    if constraint is None:
        return False

    return validate_placeholder_constraint(placeholder.raw, constraint)


def _evaluate_condition(
    *,
    block: MustBlockV1,
    context: PredicateContext,
) -> bool:
    condition = block.if_
    if condition is None:
        return True

    has_file = getattr(condition, "hasFile", None)
    if has_file is not None:
        return context.file_exists(context.resolve_template(has_file))

    placeholder_satisfies = getattr(condition, "placeholderSatisfies", None)
    if placeholder_satisfies is None:
        return False

    return _evaluate_placeholder_satisfies(
        raw=placeholder_satisfies,
        context=context,
    )
