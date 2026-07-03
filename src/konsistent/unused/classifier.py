"""Classify each definition into a verdict.

Only ``dead`` and ``test-only`` are reported; every other verdict is silent.
Priority order (first match wins): ``allowed`` -> ``hook`` -> ``registered`` ->
``model-field`` -> ``entrypoint`` -> reference-count verdicts.

Reference lookup is by bare ``name`` (not ``qualname``): a method call appears
in the index as the attribute ``name``, never ``Class.name``. Two definitions
sharing a name therefore share references — coarse, under-reporting (zero false
positives direction), documented.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Literal

from konsistent.core.diagnostics import DiagnosticSeverity
from konsistent.unused.definitions import Definition
from konsistent.unused.presets import is_dunder
from konsistent.unused.references import EMPTY_REF_STATS, ReferenceIndex

Verdict = Literal[
    "dead",
    "test-only",
    "allowed",
    "hook",
    "registered",
    "model-field",
    "entrypoint",
    "used",
]

REPORTED_VERDICTS: frozenset[Verdict] = frozenset({"dead", "test-only"})


@dataclass(frozen=True, kw_only=True)
class ResolvedUnusedConfig:
    """`UnusedCodeV1` merged with engine defaults and framework presets."""

    include: tuple[str, ...]
    test_globs: tuple[str, ...]
    entrypoint_files: tuple[str, ...]
    registry_decorators: tuple[str, ...]
    hook_names: frozenset[str]
    model_bases: frozenset[str]
    dataclass_decorators: frozenset[str]
    allow: frozenset[str]
    severity: DiagnosticSeverity


@dataclass(frozen=True, kw_only=True)
class Classification:
    """A definition's verdict and the reason it was assigned."""

    definition: Definition
    verdict: Verdict
    reason: str


def classify(
    *,
    definition: Definition,
    index: ReferenceIndex,
    config: ResolvedUnusedConfig,
) -> Classification:
    """Classify `definition` into a verdict using reference counts and config rules."""
    if definition.name in config.allow or definition.qualname in config.allow:
        return _classification(definition, "allowed", "allow-listed")

    if _is_hook(definition.name, config.hook_names):
        return _classification(definition, "hook", "framework lifecycle hook")

    if _is_registered(definition.decorators, config.registry_decorators):
        return _classification(definition, "registered", "registry decorator")

    if definition.kind == "attribute" and _is_model_field(definition, config):
        return _classification(definition, "model-field", "model field")

    stats = index.get(definition.name, EMPTY_REF_STATS)

    if stats.entrypoint > 0:
        return _classification(definition, "entrypoint", "referenced by entrypoint file")

    if stats.prod == 0 and stats.test == 0:
        return _classification(definition, "dead", "never referenced")

    if stats.prod == 0 and stats.test > 0:
        return _classification(definition, "test-only", "only referenced by tests")

    return _classification(definition, "used", "referenced")


def _classification(definition: Definition, verdict: Verdict, reason: str) -> Classification:
    return Classification(definition=definition, verdict=verdict, reason=reason)


def _is_hook(name: str, hook_names: frozenset[str]) -> bool:
    return is_dunder(name) or name in hook_names


def _is_registered(decorators: tuple[str, ...], patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatchcase(decorator, pattern) for decorator in decorators for pattern in patterns
    )


def _is_model_field(definition: Definition, config: ResolvedUnusedConfig) -> bool:
    if any(base in config.model_bases for base in definition.class_bases):
        return True
    return any(
        decorator in config.dataclass_decorators for decorator in definition.class_decorators
    )


__all__ = [
    "REPORTED_VERDICTS",
    "Classification",
    "ResolvedUnusedConfig",
    "Verdict",
    "classify",
]
