"""Build a repo-wide reference index from Python files and entrypoint files.

A reference is any identifier used somewhere other than its own definition
binding: ``ast.Name`` loads/stores, ``ast.Attribute`` ``.attr`` accesses, import
alias names, and identifier-like tokens inside string literals (this catches
``"src.module.handler"`` and ``getattr`` strings). Keyword argument *names* do
not count.

Each name maps to a :class:`RefStats` recording how many references came from
production code, test code, and declared entrypoint files, plus the set of
modules that reference it. References in the *same* module as a definition count
(recursion, ``__all__`` strings, internal calls are real usage) — a documented
limitation that keeps false positives at zero.
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z_]+")


@dataclass(frozen=True, kw_only=True)
class RefStats:
    prod: int = 0
    test: int = 0
    entrypoint: int = 0
    defining_modules: frozenset[str] = frozenset()


@dataclass(frozen=True, kw_only=True)
class PythonRefSource:
    module_path: str
    tree: ast.Module
    is_test: bool


EMPTY_REF_STATS = RefStats()

ReferenceIndex = dict[str, RefStats]


def build_reference_index(
    *,
    python_sources: Sequence[PythonRefSource],
    entrypoint_texts: Sequence[str],
) -> ReferenceIndex:
    prod: Counter[str] = Counter()
    test: Counter[str] = Counter()
    entrypoint: Counter[str] = Counter()
    modules: dict[str, set[str]] = defaultdict(set)

    for source in python_sources:
        counts = _collect_reference_counts(source.tree)
        bucket = test if source.is_test else prod
        for name, count in counts.items():
            bucket[name] += count
            modules[name].add(source.module_path)

    for text in entrypoint_texts:
        for token in _tokenize(text):
            entrypoint[token] += 1

    names = set(prod) | set(test) | set(entrypoint) | set(modules)
    return {
        name: RefStats(
            prod=prod[name],
            test=test[name],
            entrypoint=entrypoint[name],
            defining_modules=frozenset(modules[name]),
        )
        for name in names
    }


def _collect_reference_counts(tree: ast.Module) -> Counter[str]:
    skip = _binding_target_ids(tree)
    counts: Counter[str] = Counter()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if id(node) not in skip:
                counts[node.id] += 1
        elif isinstance(node, ast.Attribute):
            counts[node.attr] += 1
        elif isinstance(node, ast.Import):
            for alias in node.names:
                counts[alias.name.split(".", 1)[0]] += 1
                if alias.asname:
                    counts[alias.asname] += 1
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    counts[alias.name] += 1
                if alias.asname:
                    counts[alias.asname] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in _tokenize(node.value):
                counts[token] += 1

    return counts


def _binding_target_ids(tree: ast.Module) -> set[int]:
    """Node ids of ``Name`` targets that are a definition's own binding site.

    Mirrors the single-``Name`` targets that ``collect_definitions`` records, so
    the binding occurrence never counts as a reference to itself. Augmented
    assignment targets are *not* skipped (``x += 1`` reads ``x``).
    """

    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    skip.add(id(target))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            skip.add(id(node.target))
    return skip


def _tokenize(text: str) -> Iterator[str]:
    for token in _TOKEN_SPLIT.split(text):
        if len(token) >= 2:
            yield token


__all__ = [
    "EMPTY_REF_STATS",
    "PythonRefSource",
    "RefStats",
    "ReferenceIndex",
    "build_reference_index",
]
