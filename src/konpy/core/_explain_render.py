from __future__ import annotations

from typing import Literal

from konpy.config.schema import ConfigV1
from konpy.core._explain_model import (
    ExplainedBlock,
    ExplainedConfig,
    ExplainedConvention,
    ExplainedUnusedCode,
    build_explained_config,
)

ExplainFormat = Literal["md", "text"]

_SUPPRESSION_NOTE_MARKDOWN = (
    "Suppression comments (`konpy: ignore[rule]`) are for approved "
    "exceptions only. Never add one without explicit human approval -- see "
    "`konpy docs suppressions`. Fix the violation, or ask a human to "
    "approve a suppression with a reason."
)

_SUPPRESSION_NOTE_TEXT = (
    "Suppression comments (konpy: ignore[rule]) are for approved "
    "exceptions only. Never add one without explicit human approval -- see "
    "'konpy docs suppressions'. Fix the violation, or ask a human to "
    "approve a suppression with a reason."
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


def render_explain_markdown(explained: ExplainedConfig) -> str:
    """Render an `ExplainedConfig` as Markdown, suitable for pasting into CLAUDE.md."""
    lines: list[str] = [
        "# Project conventions",
        "",
        "Structural conventions enforced by `konpy`. Follow these before "
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
    """Render an `ExplainedConfig` as plain text."""
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
    """Render a resolved `ConfigV1` as prevention-side guidance in `format`."""
    explained = build_explained_config(config)
    if format == "text":
        return render_explain_text(explained)
    if format == "md":
        return render_explain_markdown(explained)
    raise ValueError(f"Unknown explain format: {format!r}")


__all__ = [
    "ExplainFormat",
    "render_explain",
    "render_explain_markdown",
    "render_explain_text",
]
