"""Render a resolved ConfigV1 as prevention-side guidance.

Used by `konsistent explain` to produce concise Markdown or plain-text output
describing every configured convention (name, description, hint, paths,
predicates) plus the resolved `unusedCode` settings. Intended to be pasted
into an AI coding agent's instructions file (e.g. CLAUDE.md) so the agent
follows the rules while writing code, instead of only being caught by `check`
afterwards.

Deliberately independent of core/runner.py: block-flattening logic here is a
self-contained reimplementation of the same must/mustNot/list-of-blocks shape
(rather than importing runner.py's private `_normalize_must_blocks`), to avoid
any coupling to runner internals.

Placeholders (`${name.method(...)}`) inside paths/predicate values are never
resolved here -- there is no per-file PredicateContext at explain-time -- they
are rendered verbatim.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from konsistent.config.schema import (
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
from konsistent.core.convention_name import generate_convention_name
from konsistent.predicates.registry import iter_predicate_items
from konsistent.unused import resolve_config as resolve_unused_config

ExplainFormat = Literal["md", "text"]


@dataclass(frozen=True, kw_only=True)
class ExplainedPredicate:
    key: str
    rendered: str


@dataclass(frozen=True, kw_only=True)
class ExplainedBlock:
    name: str | None
    condition: str | None
    hint: str | None = None
    must: list[ExplainedPredicate] = field(default_factory=list)
    must_not: list[ExplainedPredicate] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ExplainedConvention:
    name: str
    description: str | None
    hint: str | None
    severity: Severity
    paths: list[str]
    exclude_files: list[str]
    blocks: list[ExplainedBlock]


@dataclass(frozen=True, kw_only=True)
class ExplainedUnusedCode:
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
    conventions: list[ExplainedConvention]
    unused_code: ExplainedUnusedCode | None


def _paths_list(paths: str | list[str]) -> list[str]:
    return [paths] if isinstance(paths, str) else list(paths)


def _stringify(value: Any) -> str:
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
    return ExplainedConfig(
        conventions=[_explain_convention(c) for c in config.conventions],
        unused_code=(
            _explain_unused_code(config.unusedCode)
            if config.unusedCode is not None
            else None
        ),
    )


def _block_label(block: ExplainedBlock, index: int) -> str:
    return block.name if block.name else f"block {index + 1}"


def _block_suffix_markdown(block: ExplainedBlock, *, convention_hint: str | None) -> str:
    parts: list[str] = []
    if block.condition:
        parts.append(block.condition)
    if block.hint and block.hint != convention_hint:
        parts.append(f"hint: {block.hint}")
    return f" — {'; '.join(parts)}" if parts else ""


def _render_convention_markdown(c: ExplainedConvention) -> list[str]:
    paths = ", ".join(f"`{p}`" for p in c.paths)
    lines = [f"- **`{c.name}`** (severity: `{c.severity}`) — paths: {paths}"]

    if c.description:
        lines.append(f"  - {c.description}")
    if c.hint:
        lines.append(f"  - hint: {c.hint}")
    if c.exclude_files:
        excludes = ", ".join(f"`{p}`" for p in c.exclude_files)
        lines.append(f"  - excludes: {excludes}")

    multiple_blocks = len(c.blocks) > 1
    for index, block in enumerate(c.blocks):
        label = _block_label(block, index) if multiple_blocks else None
        suffix = _block_suffix_markdown(block, convention_hint=c.hint)
        if block.must:
            body = "; ".join(f"`{p.key}` {p.rendered}" for p in block.must)
            prefix = f"must ({label}): " if label else "must: "
            lines.append(f"  - {prefix}{body}{suffix}")
        if block.must_not:
            body = "; ".join(f"`{p.key}` {p.rendered}" for p in block.must_not)
            prefix = f"must not ({label}): " if label else "must not: "
            lines.append(f"  - {prefix}{body}{suffix}")

    return lines


def _render_unused_code_lines(
    u: ExplainedUnusedCode,
    *,
    quote: str,
) -> list[str]:
    def fmt(label: str, values: list[str]) -> str:
        if not values:
            placeholder = "(none configured)" if quote == "" else "_(none configured)_"
            return f"- {label}: {placeholder}"
        rendered = ", ".join(f"{quote}{v}{quote}" for v in values)
        return f"- {label}: {rendered}"

    return [
        f"- severity: {quote}{u.severity}{quote}",
        fmt("included paths", u.include),
        fmt("test paths", u.test_globs),
        fmt("entrypoint files", u.entrypoint_files),
        fmt("registry decorator patterns treated as used", u.registry_decorators),
        fmt("hook / lifecycle names treated as used", u.hook_names),
        fmt("model base classes whose attributes count as used", u.model_bases),
        fmt("explicitly allowed dead-code names", u.allow),
    ]


_SUPPRESSION_NOTE_MARKDOWN = (
    "Suppression comments (`konsistent: ignore[rule]`) are for approved "
    "exceptions only. Never add one without explicit human approval -- see "
    "`docs/reference/suppressions.md`. Fix the violation, or ask a human to "
    "approve a suppression with a reason."
)

_SUPPRESSION_NOTE_TEXT = (
    "Suppression comments (konsistent: ignore[rule]) are for approved "
    "exceptions only. Never add one without explicit human approval -- see "
    "docs/reference/suppressions.md. Fix the violation, or ask a human to "
    "approve a suppression with a reason."
)


def render_explain_markdown(explained: ExplainedConfig) -> str:
    lines: list[str] = [
        "# Project conventions",
        "",
        "Structural conventions enforced by `konsistent`. Follow these before "
        "writing or editing Python files in this repository.",
        "",
        "## Conventions",
        "",
    ]

    if explained.conventions:
        for convention in explained.conventions:
            lines.extend(_render_convention_markdown(convention))
    else:
        lines.append("_No conventions configured._")

    if explained.unused_code is not None:
        lines.append("")
        lines.append("## Unused code")
        lines.append("")
        lines.extend(_render_unused_code_lines(explained.unused_code, quote="`"))

    lines.append("")
    lines.append("## Suppressions")
    lines.append("")
    lines.append(_SUPPRESSION_NOTE_MARKDOWN)

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _block_suffix_text(block: ExplainedBlock, *, convention_hint: str | None) -> str:
    parts: list[str] = []
    if block.condition:
        parts.append(block.condition)
    if block.hint and block.hint != convention_hint:
        parts.append(f"hint: {block.hint}")
    return f" -- {'; '.join(parts)}" if parts else ""


def _render_convention_text(c: ExplainedConvention) -> list[str]:
    paths = ", ".join(c.paths)
    lines = [f"- {c.name} (severity: {c.severity}) - paths: {paths}"]

    if c.description:
        lines.append(f"    {c.description}")
    if c.hint:
        lines.append(f"    hint: {c.hint}")
    if c.exclude_files:
        lines.append(f"    excludes: {', '.join(c.exclude_files)}")

    multiple_blocks = len(c.blocks) > 1
    for index, block in enumerate(c.blocks):
        label = _block_label(block, index) if multiple_blocks else None
        suffix = _block_suffix_text(block, convention_hint=c.hint)
        if block.must:
            body = "; ".join(f"{p.key} {p.rendered}" for p in block.must)
            prefix = f"must ({label}): " if label else "must: "
            lines.append(f"    {prefix}{body}{suffix}")
        if block.must_not:
            body = "; ".join(f"{p.key} {p.rendered}" for p in block.must_not)
            prefix = f"must not ({label}): " if label else "must not: "
            lines.append(f"    {prefix}{body}{suffix}")

    return lines


def render_explain_text(explained: ExplainedConfig) -> str:
    lines: list[str] = ["Project conventions", "", "Conventions:"]

    if explained.conventions:
        for convention in explained.conventions:
            lines.extend(_render_convention_text(convention))
    else:
        lines.append("(none configured)")

    if explained.unused_code is not None:
        lines.append("")
        lines.append("Unused code:")
        lines.extend(_render_unused_code_lines(explained.unused_code, quote=""))

    lines.append("")
    lines.append("Suppressions:")
    lines.append(_SUPPRESSION_NOTE_TEXT)

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def render_explain(config: ConfigV1, *, format: ExplainFormat = "md") -> str:
    explained = build_explained_config(config)
    if format == "text":
        return render_explain_text(explained)
    if format == "md":
        return render_explain_markdown(explained)
    raise ValueError(f"Unknown explain format: {format!r}")


__all__ = [
    "ExplainFormat",
    "ExplainedBlock",
    "ExplainedConfig",
    "ExplainedConvention",
    "ExplainedPredicate",
    "ExplainedUnusedCode",
    "build_explained_config",
    "render_explain",
    "render_explain_markdown",
    "render_explain_text",
]
