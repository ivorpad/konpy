"""Shared small types used across the `run()` implementation modules."""

from __future__ import annotations

from dataclasses import dataclass

from konpy.config.schema import MustPredicatesV1

CaseMaps = dict[str, dict[str, str] | None]


@dataclass(frozen=True, kw_only=True)
class _MustNotCheck:
    key: str
    predicate: MustPredicatesV1
    value: object


@dataclass(frozen=True, kw_only=True)
class _ForbiddenFixData:
    expected: str | None = None
    found: str | None = None
    fix_hint: str | None = None
    line: int | None = None
    column: int | None = None
