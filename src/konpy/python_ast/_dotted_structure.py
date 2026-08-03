from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from konpy.python_ast._structure_shared import SourcePosition


@dataclass(frozen=True, kw_only=True)
class DecoratorInfo:
    """A decorator occurrence on a function or class, written and resolved."""

    written: str
    resolved: str
    pos: SourcePosition
    target_kind: Literal["function", "class"]
    target_qualified_name: str
    is_call: bool


@dataclass(frozen=True, kw_only=True)
class CallSiteInfo:
    """A call expression, with its callee written and resolved dotted path."""

    written: str
    resolved: str
    pos: SourcePosition
    scope: Literal["module", "class", "function"]


@dataclass(frozen=True, kw_only=True)
class BaseClassRefInfo:
    """A single base-class reference in a class's bases list."""

    written: str
    resolved: str
    pos: SourcePosition
    class_qualified_name: str


@dataclass(frozen=True, kw_only=True)
class ScopedImportInfo:
    """An import binding recorded with the scope it executes in."""

    source: str
    symbol_path: str
    pos: SourcePosition
    scope: Literal["module", "function"]
    is_type: bool


__all__: list[str] = []
