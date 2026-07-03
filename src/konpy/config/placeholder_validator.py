from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from konpy.config._placeholder_block_collectors import _collect_usages_in_assertions
from konpy.config._placeholder_shared import (
    DECLARATION_REGEX,
    USAGE_REGEX,
    _collect_declarations,
    _to_alias_dict,
)
from konpy.config.errors import Err, Ok, Result
from konpy.config.schema import ConventionV1

if TYPE_CHECKING:
    # konpy.predicates.registry imports konpy.config.schema at module
    # level, so importing it unconditionally here would cycle back through
    # this package's __init__; PredicateRegistry is only used in annotations.
    from konpy.predicates.registry import PredicateRegistry


def validate_placeholders(
    *,
    conventions: Sequence[ConventionV1],
    identifiers: Sequence[str],
    predicate_registry: PredicateRegistry | None = None,
) -> Result[None]:
    """Check that every ${name} placeholder used in a convention is declared by its paths."""
    errors: list[str] = []

    for index, convention in enumerate(conventions):
        convention_data = _to_alias_dict(convention)
        identifier = identifiers[index] if index < len(identifiers) else f"conventions[{index}]"

        declared_from_paths = _collect_declarations(convention_data["paths"])
        declared = set(declared_from_paths)

        for name in convention_data.get("placeholders", {}):
            if name in declared_from_paths:
                errors.append(
                    f'Convention "{identifier}" declares placeholder "{name}" both in paths '
                    f'(as "{{{name}}}") and in placeholders. Pick one.'
                )
                continue
            declared.add(name)

        usages = _collect_usages_in_assertions(
            must=convention_data.get("must"),
            must_not=convention_data.get("mustNot"),
            declared_outer=declared,
            predicate_registry=predicate_registry,
        )

        reported: set[str] = set()
        for usage in usages:
            if usage.name in reported:
                continue
            reported.add(usage.name)
            errors.append(
                f'Convention "{identifier}" references "${{{usage.name}}}" in {usage.key}, '
                f'but neither paths nor placeholders declare "{{{usage.name}}}".'
            )

    if errors:
        return Err("\n".join(errors))
    return Ok(None)


__all__ = ["DECLARATION_REGEX", "USAGE_REGEX", "validate_placeholders"]
