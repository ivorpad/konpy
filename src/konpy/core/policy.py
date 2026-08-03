"""Resolve a `ConfigV1` into an `EffectivePolicy`: the single place that owns
per-convention name/severity/exclude-files/block-shape normalization.

Both `core/runner.py` (to evaluate against a filesystem) and
`core/_explain_model.py` (to render agent-facing guidance) consume the same
`EffectivePolicy`, so name generation, severity defaulting, and
`must`/`mustNot` block normalization happen in exactly one place. This module
does no filesystem matching and no predicate evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

from konpy.config.schema import (
    ConfigV1,
    ConventionV1,
    MustBlockV1,
    MustPredicatesV1,
    PlaceholdersMap,
    UnusedCodeV1,
)
from konpy.core.convention_name import generate_convention_name
from konpy.core.diagnostics import DiagnosticSeverity
from konpy.predicates.registry import PredicateRegistry


@dataclass(frozen=True, kw_only=True)
class EffectiveConvention:
    """One convention after name/severity/exclude-files/block normalization."""

    name: str
    description: str | None
    hint: str | None
    severity: DiagnosticSeverity
    paths: tuple[str, ...]
    exclude_files: tuple[str, ...]
    placeholders: PlaceholdersMap | None
    blocks: tuple[MustBlockV1, ...]


@dataclass(frozen=True, kw_only=True)
class EffectivePolicy:
    """A resolved `ConfigV1`: normalized conventions plus optional unused-code settings."""

    conventions: tuple[EffectiveConvention, ...]
    unused_code: UnusedCodeV1 | None


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


def _resolve_convention(
    convention: ConventionV1,
    *,
    predicate_registry: PredicateRegistry,
) -> EffectiveConvention:
    blocks = _normalize_must_blocks(
        must=convention.must,
        must_not=convention.mustNot,
        predicate_registry=predicate_registry,
    )
    name = convention.name or generate_convention_name(
        must=convention.must,
        must_not=convention.mustNot,
        predicate_registry=predicate_registry,
    )
    paths = convention.paths if isinstance(convention.paths, list) else [convention.paths]

    return EffectiveConvention(
        name=name,
        description=convention.description,
        hint=convention.hint,
        severity=convention.severity or "error",
        paths=tuple(paths),
        exclude_files=tuple(convention.excludeFiles or []),
        placeholders=convention.placeholders,
        blocks=tuple(blocks),
    )


def resolve_effective_policy(
    config: ConfigV1,
    *,
    predicate_registry: PredicateRegistry,
) -> EffectivePolicy:
    """Resolve every convention in `config` into its `EffectiveConvention` form.

    Owns name resolution (always passing `predicate_registry` to
    `generate_convention_name`), severity defaulting, `paths` listification,
    `excludeFiles` normalization, and `must`/`mustNot` block normalization.
    Does no filesystem matching and no predicate evaluation -- see
    `core/runner.py` for that.
    """
    return EffectivePolicy(
        conventions=tuple(
            _resolve_convention(convention, predicate_registry=predicate_registry)
            for convention in config.conventions
        ),
        unused_code=config.unusedCode,
    )


__all__ = ["EffectiveConvention", "EffectivePolicy", "resolve_effective_policy"]
