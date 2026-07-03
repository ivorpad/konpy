"""Placeholder-usage scanning across a convention's must/mustNot blocks.

Handles the "for"/"if"/"excludeFiles" scoping wrapper around a predicate
block before delegating to _collect_usages_in_predicates for the predicates
themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from konsistent.config._placeholder_predicate_usages import _collect_usages_in_predicates
from konsistent.config._placeholder_shared import (
    _add_declarations_from_string,
    _push_string_usages,
    _to_alias_dict,
    _Usage,
)

if TYPE_CHECKING:
    # konsistent.predicates.registry imports konsistent.config.schema at module
    # level, so importing it unconditionally here would cycle back through
    # this package's __init__; PredicateRegistry is only used in annotations.
    from konsistent.predicates.registry import PredicateRegistry


def _collect_usages_in_assertions(
    *,
    must: object,
    must_not: object,
    declared_outer: set[str],
    predicate_registry: PredicateRegistry | None,
) -> list[_Usage]:
    usages: list[_Usage] = []

    if isinstance(must, list):
        for block in must:
            _collect_usages_in_block(
                block=_to_alias_dict(block),
                declared_outer=declared_outer,
                usages=usages,
                predicate_registry=predicate_registry,
            )
    elif must is not None:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(must),
            prefix="must",
            declared=declared_outer,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    if must_not is not None:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(must_not),
            prefix="mustNot",
            declared=declared_outer,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    return usages


def _collect_usages_in_block(
    *,
    block: dict[str, object],
    declared_outer: set[str],
    usages: list[_Usage],
    predicate_registry: PredicateRegistry | None,
) -> None:
    declared_here = set(declared_outer)

    if "for" in block:
        for_data = _to_alias_dict(block["for"])
        files = for_data["files"]
        file_entries = [files] if isinstance(files, str) else files
        for file_entry in file_entries:
            _add_declarations_from_string(value=file_entry, into=declared_here)
            _push_string_usages(
                value=file_entry,
                key="must.for.files",
                declared=declared_outer,
                usages=usages,
            )

    if "if" in block:
        if_data = _to_alias_dict(block["if"])
        if "hasFile" in if_data:
            _push_string_usages(
                value=if_data["hasFile"],
                key="must.if.hasFile",
                declared=declared_here,
                usages=usages,
            )
        elif "placeholderSatisfies" in if_data:
            _push_string_usages(
                value=if_data["placeholderSatisfies"],
                key="must.if.placeholderSatisfies",
                declared=declared_here,
                usages=usages,
            )

    for file_entry in block.get("excludeFiles", []):
        _push_string_usages(
            value=file_entry,
            key="must.excludeFiles",
            declared=declared_here,
            usages=usages,
        )

    if "must" in block:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(block["must"]),
            prefix="must",
            declared=declared_here,
            usages=usages,
            predicate_registry=predicate_registry,
        )

    if "mustNot" in block:
        _collect_usages_in_predicates(
            predicates=_to_alias_dict(block["mustNot"]),
            prefix="mustNot",
            declared=declared_here,
            usages=usages,
            predicate_registry=predicate_registry,
        )


__all__: list[str] = []
