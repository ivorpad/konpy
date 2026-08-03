from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from konpy.config.schema import (
    ConditionV1,
    ConfigV1,
    ForV1,
    HasFileConditionV1,
    MustBlockV1,
    MustPredicatesV1,
    PlaceholderSatisfiesConditionV1,
    Severity,
    UnusedCodeV1,
)
from konpy.core.policy import EffectiveConvention, resolve_effective_policy
from konpy.predicates.registry import (
    PredicateRegistry,
    builtin_predicate_registry,
    iter_predicate_items,
)
from konpy.unused import resolve_config as resolve_unused_config


@dataclass(frozen=True, kw_only=True)
class ExplainedPredicate:
    """A single `must`/`mustNot` predicate rendered as a key/value pair."""

    key: str
    rendered: str


@dataclass(frozen=True, kw_only=True)
class ExplainedBlock:
    """One `must`/`mustNot` block of a convention, with its condition and hint."""

    name: str | None
    condition: str | None
    hint: str | None = None
    must: list[ExplainedPredicate] = field(default_factory=list)
    must_not: list[ExplainedPredicate] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ExplainedConvention:
    """A resolved convention flattened into a name, paths, and rendered blocks."""

    name: str
    description: str | None
    hint: str | None
    severity: Severity
    paths: list[str]
    exclude_files: list[str]
    blocks: list[ExplainedBlock]


@dataclass(frozen=True, kw_only=True)
class ExplainedUnusedCode:
    """The resolved `unusedCode` settings, rendered for display."""

    severity: Severity
    include: list[str]
    test_globs: list[str]
    entrypoint_files: list[str]
    registry_decorators: list[str]
    hook_names: list[str]
    model_bases: list[str]
    allow: list[str]


@dataclass(frozen=True, kw_only=True)
class ExplainedConfig:
    """A resolved `ConfigV1`, flattened into explain-ready conventions and unused-code settings."""

    conventions: list[ExplainedConvention]
    unused_code: ExplainedUnusedCode | None


def _stringify(value: object) -> str:
    if isinstance(value, BaseModel):
        return _stringify(value.model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k}={_stringify(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _explain_predicates(must: MustPredicatesV1) -> list[ExplainedPredicate]:
    return [
        ExplainedPredicate(key=key, rendered=_stringify(value))
        for key, value in iter_predicate_items(must)
    ]


def _condition_str(*, if_: ConditionV1 | None, for_: ForV1 | None) -> str | None:
    if if_ is None and for_ is None:
        return None

    parts: list[str] = []
    if isinstance(if_, HasFileConditionV1):
        parts.append(f"hasFile: `{if_.hasFile}`")
    elif isinstance(if_, PlaceholderSatisfiesConditionV1):
        parts.append(f"placeholderSatisfies: `{if_.placeholderSatisfies}`")

    if for_ is not None:
        files = for_.files if isinstance(for_.files, list) else [for_.files]
        rendered_files = ", ".join(f"`{f}`" for f in files)
        parts.append(f"for files matching {rendered_files}")

    return "only when " + "; ".join(parts)


def _block_from_must_block(block: MustBlockV1, *, convention_hint: str | None) -> ExplainedBlock:
    condition_parts: list[str] = []
    condition = _condition_str(if_=block.if_, for_=block.for_)
    if condition is not None:
        condition_parts.append(condition)
    if block.excludeFiles:
        excludes = ", ".join(f"`{p}`" for p in block.excludeFiles)
        condition_parts.append(f"except files matching {excludes}")

    return ExplainedBlock(
        name=block.name,
        condition="; ".join(condition_parts) if condition_parts else None,
        hint=block.hint or convention_hint,
        must=_explain_predicates(block.must) if block.must is not None else [],
        must_not=_explain_predicates(block.mustNot) if block.mustNot is not None else [],
    )


def _explain_blocks(convention: EffectiveConvention) -> list[ExplainedBlock]:
    return [
        _block_from_must_block(block, convention_hint=convention.hint)
        for block in convention.blocks
    ]


def _explain_convention(convention: EffectiveConvention) -> ExplainedConvention:
    return ExplainedConvention(
        name=convention.name,
        description=convention.description,
        hint=convention.hint,
        severity=convention.severity,
        paths=list(convention.paths),
        exclude_files=list(convention.exclude_files),
        blocks=_explain_blocks(convention),
    )


def _explain_unused_code(unused: UnusedCodeV1) -> ExplainedUnusedCode:
    resolved = resolve_unused_config(unused)
    return ExplainedUnusedCode(
        severity=resolved.severity,
        include=list(resolved.include),
        test_globs=list(resolved.test_globs),
        entrypoint_files=list(resolved.entrypoint_files),
        registry_decorators=list(resolved.registry_decorators),
        hook_names=sorted(resolved.hook_names),
        model_bases=sorted(resolved.model_bases),
        allow=sorted(resolved.allow),
    )


def build_explained_config(
    config: ConfigV1,
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> ExplainedConfig:
    """Flatten a resolved `ConfigV1` into explain-ready conventions and unused-code settings.

    Resolves the same `EffectivePolicy` that `core.runner.run()` evaluates
    (via `core.policy.resolve_effective_policy`), so name/severity/exclude-
    files/block normalization can never drift between `check` and `explain`.
    `predicate_registry` should be the actual registry the config was loaded
    with (plugin predicates affect nothing here today, since
    `generate_convention_name` doesn't consult it, but passing it keeps this
    call site correct if that ever changes); it defaults to the builtin
    registry for direct callers that never installed plugins.
    """
    registry = predicate_registry or builtin_predicate_registry()
    policy = resolve_effective_policy(config, predicate_registry=registry)
    return ExplainedConfig(
        conventions=[_explain_convention(c) for c in policy.conventions],
        unused_code=(
            _explain_unused_code(policy.unused_code)
            if policy.unused_code is not None
            else None
        ),
    )


__all__ = [
    "ExplainedBlock",
    "ExplainedConfig",
    "ExplainedConvention",
    "ExplainedPredicate",
    "ExplainedUnusedCode",
    "build_explained_config",
]
