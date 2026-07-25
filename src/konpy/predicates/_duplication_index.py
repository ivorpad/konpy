from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from konpy.predicates._wildcards import _matches_any
from konpy.python_ast.structure import PyFileStructure, SourcePosition

type _RepeatedLiteralIndex = dict[str, tuple["_StringLiteralOccurrence", ...]]
type _DuplicateFunctionIndex = dict[str, "_DuplicateFunctionGroup"]


@dataclass(frozen=True, kw_only=True)
class _StringLiteralOccurrence:
    file_path: str
    value: str
    pos: SourcePosition
    is_mapping_key: bool = False


@dataclass(frozen=True, kw_only=True)
class _FunctionFingerprintOccurrence:
    file_path: str
    name: str
    qualified_name: str
    is_public: bool
    pos: SourcePosition
    fingerprint: str
    statement_count: int


@dataclass(frozen=True, kw_only=True)
class _DuplicateFunctionGroup:
    canonical: _FunctionFingerprintOccurrence
    duplicates: tuple[_FunctionFingerprintOccurrence, ...]


def _build_repeated_literal_index(
    structures: Mapping[str, PyFileStructure],
    *,
    min_length: int,
    max_occurrences: int,
    allow: tuple[str, ...],
) -> _RepeatedLiteralIndex:
    groups: dict[str, list[_StringLiteralOccurrence]] = {}

    for file_path in sorted(structures):
        for literal in structures[file_path].string_literals:
            if len(literal.value) < min_length:
                continue
            if _matches_any(literal.value, allow):
                continue
            groups.setdefault(literal.value, []).append(
                _StringLiteralOccurrence(
                    file_path=file_path,
                    value=literal.value,
                    pos=literal.pos,
                    is_mapping_key=literal.is_mapping_key,
                )
            )

    return {
        value: tuple(sorted(occurrences, key=_literal_sort_key))
        for value, occurrences in sorted(groups.items())
        if len(occurrences) > max_occurrences
    }


def _build_duplicate_function_index(
    structures: Mapping[str, PyFileStructure],
    *,
    min_statements: int,
    public_only: bool,
    allow_names: tuple[str, ...],
) -> _DuplicateFunctionIndex:
    groups: dict[str, list[_FunctionFingerprintOccurrence]] = {}

    for file_path in sorted(structures):
        for function in structures[file_path].function_fingerprints:
            occurrence = _FunctionFingerprintOccurrence(
                file_path=file_path,
                name=function.name,
                qualified_name=function.qualified_name,
                is_public=function.is_public,
                pos=function.pos,
                fingerprint=function.fingerprint,
                statement_count=function.statement_count,
            )
            if occurrence.statement_count < min_statements:
                continue
            if public_only and not occurrence.is_public:
                continue
            if _function_name_allowed(occurrence, allow_names):
                continue
            groups.setdefault(occurrence.fingerprint, []).append(occurrence)

    duplicate_groups: _DuplicateFunctionIndex = {}
    for fingerprint, occurrences in sorted(groups.items()):
        if len(occurrences) <= 1:
            continue
        ordered = tuple(sorted(occurrences, key=_function_sort_key))
        duplicate_groups[fingerprint] = _DuplicateFunctionGroup(
            canonical=ordered[0],
            duplicates=ordered[1:],
        )

    return duplicate_groups


def _function_name_allowed(
    occurrence: _FunctionFingerprintOccurrence,
    allow_names: tuple[str, ...],
) -> bool:
    candidates = (
        occurrence.name,
        occurrence.qualified_name,
        f"{occurrence.file_path}::{occurrence.qualified_name}",
    )
    return any(_matches_any(candidate, allow_names) for candidate in candidates)


def _literal_sort_key(
    occurrence: _StringLiteralOccurrence,
) -> tuple[str, int, int, str]:
    return (
        occurrence.file_path,
        occurrence.pos.line,
        occurrence.pos.column,
        occurrence.value,
    )


def _function_sort_key(
    occurrence: _FunctionFingerprintOccurrence,
) -> tuple[str, int, int, str]:
    return (
        occurrence.file_path,
        occurrence.pos.line,
        occurrence.pos.column,
        occurrence.qualified_name,
    )


__all__: list[str] = []
