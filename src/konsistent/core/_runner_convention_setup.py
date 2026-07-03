"""Per-convention setup: normalizing `must`/`mustNot` into blocks, and
attaching convention-level description/hint metadata to their diagnostics.
"""

from __future__ import annotations

from dataclasses import replace

from konsistent.config.schema import MustBlockV1, MustPredicatesV1
from konsistent.core.diagnostics import Diagnostic
from konsistent.predicates.registry import PredicateRegistry


def _normalize_must_blocks(
    *,
    must: MustPredicatesV1 | list[MustBlockV1] | None,
    must_not: MustPredicatesV1 | None,
    predicate_registry: PredicateRegistry,
) -> list[MustBlockV1]:
    context = predicate_registry.validation_context()

    if isinstance(must, list):
        blocks = list(must)
        if must_not is not None:
            blocks.append(MustBlockV1.model_validate({"mustNot": must_not}, context=context))
        return blocks

    if must is not None and must_not is not None:
        return [
            MustBlockV1.model_validate(
                {"must": must, "mustNot": must_not},
                context=context,
            )
        ]

    if must is not None:
        return [MustBlockV1.model_validate({"must": must}, context=context)]

    if must_not is not None:
        return [MustBlockV1.model_validate({"mustNot": must_not}, context=context)]

    return []


def _with_convention_metadata(
    diagnostics: list[Diagnostic],
    *,
    description: str | None,
    hint: str | None,
) -> list[Diagnostic]:
    if description is None and hint is None:
        return diagnostics

    return [
        replace(
            diagnostic,
            description=diagnostic.description or description,
            hint=diagnostic.hint or hint,
        )
        for diagnostic in diagnostics
    ]
