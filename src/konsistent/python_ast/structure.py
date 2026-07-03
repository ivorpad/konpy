from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExportKind = Literal["function", "class", "protocol", "const", "type", "re-export"]
DeclarationSymbolKind = Literal["function", "class", "protocol", "type", "const"]
NonBarrelStatementKind = Literal["declaration", "expression"]
DocstringTargetKind = Literal["module", "class", "function"]


@dataclass(frozen=True, kw_only=True)
class SourcePosition:
    """A 1-based line/column location in a source file."""

    column: int
    line: int


@dataclass(frozen=True, kw_only=True)
class DocstringTargetInfo:
    """A module, class, or function considered for docstring coverage."""

    kind: DocstringTargetKind
    name: str
    qualified_name: str
    is_public: bool
    has_docstring: bool
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ExportInfo:
    """A public symbol exported from a module."""

    from_: str | None
    is_type: bool
    kind: ExportKind
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ImportInfo:
    """A single imported name bound in a module."""

    from_: str
    is_type: bool
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class DeclarationSymbolInfo:
    """A top-level function, class, type, or constant declaration."""

    is_default_export: bool
    is_exported: bool
    kind: DeclarationSymbolKind
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class NamedExportSymbolInfo:
    """A named re-export, tracking its original source name."""

    from_: str | None
    is_type: bool
    name: str
    pos: SourcePosition
    source_name: str


@dataclass(frozen=True, kw_only=True)
class DefaultExportSymbolInfo:
    """A default-export symbol (kept for TS-grammar parity)."""

    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ImportSourceInfo:
    """The module a set of imports were sourced from."""

    from_: str
    is_type: bool
    pos: SourcePosition
    level: int


@dataclass(frozen=True, kw_only=True)
class ExtendsClauseInfo:
    """A single base class in an `extends`-style clause."""

    name: str
    type_arguments: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class TypeAnnotationInfo:
    """A parsed type annotation, with its unsubscripted base name."""

    base_name: str
    text: str


@dataclass(frozen=True, kw_only=True)
class InterfaceInfo:
    """A Protocol or ABC class, treated as an interface declaration."""

    extends: tuple[ExtendsClauseInfo, ...]
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ClassInfo:
    """A class declaration with its base class and mixins."""

    extends: str | None
    implements: tuple[str, ...]
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ParamInfo:
    """A single function parameter and its optional type annotation."""

    name: str
    type_name: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class FunctionInfo:
    """A function declaration with its parameters and return type."""

    name: str
    params: tuple[ParamInfo, ...]
    pos: SourcePosition
    return_type: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class FunctionAnnotationInfo:
    """A function or method considered for parameter/return annotation coverage."""

    name: str
    qualified_name: str
    is_public: bool
    params: tuple[ParamInfo, ...]
    pos: SourcePosition
    return_type: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class ConstantInfo:
    """A module-level constant declaration."""

    name: str
    pos: SourcePosition
    type_name: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class TypeAliasInfo:
    """A `type` statement or `TypeAlias`-annotated assignment."""

    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class NonBarrelStatementInfo:
    """A module-level statement that disqualifies a file from being a barrel."""

    kind: NonBarrelStatementKind
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class PyFileStructure:
    """The full structural summary of a parsed Python source file."""

    classes: tuple[ClassInfo, ...]
    constants: tuple[ConstantInfo, ...]
    declaration_symbols: tuple[DeclarationSymbolInfo, ...]
    default_export_symbols: tuple[DefaultExportSymbolInfo, ...]
    docstring_targets: tuple[DocstringTargetInfo, ...]
    exports: tuple[ExportInfo, ...]
    function_annotation_targets: tuple[FunctionAnnotationInfo, ...]
    functions: tuple[FunctionInfo, ...]
    import_sources: tuple[ImportSourceInfo, ...]
    imports: tuple[ImportInfo, ...]
    interfaces: tuple[InterfaceInfo, ...]
    named_export_symbols: tuple[NamedExportSymbolInfo, ...]
    non_barrel_statements: tuple[NonBarrelStatementInfo, ...]
    type_aliases: tuple[TypeAliasInfo, ...]
    all_names: tuple[str, ...] | None
    all_is_dynamic: bool


__all__ = [
    "ClassInfo",
    "ConstantInfo",
    "DeclarationSymbolInfo",
    "DeclarationSymbolKind",
    "DefaultExportSymbolInfo",
    "DocstringTargetInfo",
    "DocstringTargetKind",
    "ExportInfo",
    "ExportKind",
    "ExtendsClauseInfo",
    "FunctionAnnotationInfo",
    "FunctionInfo",
    "ImportInfo",
    "ImportSourceInfo",
    "InterfaceInfo",
    "NamedExportSymbolInfo",
    "NonBarrelStatementInfo",
    "NonBarrelStatementKind",
    "ParamInfo",
    "PyFileStructure",
    "SourcePosition",
    "TypeAliasInfo",
    "TypeAnnotationInfo",
]
