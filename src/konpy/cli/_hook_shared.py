"""Payload-to-target resolution shared by `konpy hook` and `konpy review`.

Both commands parse the same PostToolUse payload shape down to the same
"which paths, which rule batches" question before diverging on how a
verified fail verdict is handled (blocking vs. advisory). This module holds
that shared resolution step plus the small helpers it depends on, so neither
command has to re-derive it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from konpy.cli._hook_support import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOLS,
    HookPayload,
    extract_target_paths,
    parse_hook_payload,
    path_matches_any,
)
from konpy.cli._semantic_rules import SemanticRulesPackageV1, SemanticRuleV1


@dataclass(frozen=True, kw_only=True)
class ResolvedHookTarget:
    """Matched write paths and, in rules mode, their applicable rule batches."""

    payload: HookPayload
    matched_paths: list[str]
    batches: list[tuple[str, list[SemanticRuleV1]]]


def resolve_hook_target(
    *,
    raw_stdin: str,
    match: list[str],
    rules_package: SemanticRulesPackageV1 | None,
) -> ResolvedHookTarget | None:
    """Parse a hook payload down to matched write paths and rule batches.

    Returns `None` for every case that should skip silently: an unparseable
    payload, a non-write tool, no target path matching `match`, or (in rules
    mode) no target path with any applicable rule.
    """
    payload = parse_hook_payload(raw_stdin)
    if payload is None:
        return None
    if payload.tool_name not in (CLAUDE_WRITE_TOOLS | CODEX_WRITE_TOOLS):
        return None

    target_paths = extract_target_paths(payload)
    matched_paths = [path for path in target_paths if path_matches_any(path, match)]
    if not matched_paths:
        return None

    batches: list[tuple[str, list[SemanticRuleV1]]] = []
    if rules_package is not None:
        for path in dedupe_paths(matched_paths):
            applicable = [
                rule
                for rule in rules_package.rules
                if path_matches_any(path, rule.match)
            ]
            if applicable:
                batches.append((path, applicable))
        if not batches:
            return None

    return ResolvedHookTarget(
        payload=payload,
        matched_paths=matched_paths,
        batches=batches,
    )


def dedupe_paths(paths: Sequence[str]) -> list[str]:
    """Deduplicate paths, preserving first-seen order."""
    return list(dict.fromkeys(paths))


__all__ = ["ResolvedHookTarget", "dedupe_paths", "resolve_hook_target"]
