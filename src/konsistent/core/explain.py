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

from konsistent.core._explain_model import (
    ExplainedBlock,
    ExplainedConfig,
    ExplainedConvention,
    ExplainedPredicate,
    ExplainedUnusedCode,
    build_explained_config,
)
from konsistent.core._explain_render import (
    ExplainFormat,
    render_explain,
    render_explain_markdown,
    render_explain_text,
)

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
