from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from konpy.config.schema import (
    ConditionV1,
    ConfigV1,
    ConventionV1,
    ForV1,
    HasFileConditionV1,
    MustBlockV1,
    MustPredicatesV1,
    PlaceholderSatisfiesConditionV1,
    Severity,
    UnusedCodeV1,
)
from konpy.core.convention_name import generate_convention_name
from konpy.predicates.registry import iter_predicate_items
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


def _paths_list(paths: str | list[str]) -> list[str]:
    return [paths] if isinstance(paths, str) else list(paths)


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


def _block_from_must_block(block: MustBlockV1, *, convention: ConventionV1) -> ExplainedBlock:
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
        hint=block.hint or convention.hint,
        must=_explain_predicates(block.must) if block.must is not None else [],
        must_not=_explain_predicates(block.mustNot) if block.mustNot is not None else [],
    )


def _explain_blocks(convention: ConventionV1) -> list[ExplainedBlock]:
    if isinstance(convention.must, list):
        blocks = [_block_from_must_block(block, convention=convention) for block in convention.must]
        if convention.mustNot is not None:
            blocks.append(
                ExplainedBlock(
                    name=None,
                    condition=None,
                    hint=convention.hint,
                    must_not=_explain_predicates(convention.mustNot),
                )
            )
        return blocks

    if convention.must is not None or convention.mustNot is not None:
        return [
            ExplainedBlock(
                name=None,
                condition=None,
                hint=convention.hint,
                must=(
                    _explain_predicates(convention.must)
                    if convention.must is not None
                    else []
                ),
                must_not=(
                    _explain_predicates(convention.mustNot)
                    if convention.mustNot is not None
                    else []
                ),
            )
        ]

    # Unreachable given _RequiresMustOrMustNot, kept for defensive completeness.
    return []


def _explain_convention(convention: ConventionV1) -> ExplainedConvention:
    resolved_name = convention.name or generate_convention_name(
        must=convention.must,
        must_not=convention.mustNot,
    )
    return ExplainedConvention(
        name=resolved_name,
        description=convention.description,
        hint=convention.hint,
        severity=convention.severity or "error",
        paths=_paths_list(convention.paths),
        exclude_files=list(convention.excludeFiles or []),
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


def build_explained_config(config: ConfigV1) -> ExplainedConfig:
    """Flatten a resolved `ConfigV1` into explain-ready conventions and unused-code settings."""
    return ExplainedConfig(
        conventions=[_explain_convention(c) for c in config.conventions],
        unused_code=(
            _explain_unused_code(config.unusedCode)
            if config.unusedCode is not None
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
