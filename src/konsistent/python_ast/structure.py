from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExportKind = Literal["function", "class", "protocol", "const", "type", "re-export"]
DeclarationSymbolKind = Literal["function", "class", "protocol", "type", "const"]
NonBarrelStatementKind = Literal["declaration", "expression"]
DocstringTargetKind = Literal["module", "class", "function"]


@dataclass(frozen=True, kw_only=True)
class SourcePosition:
    column: int
    line: int


@dataclass(frozen=True, kw_only=True)
class DocstringTargetInfo:
    kind: DocstringTargetKind
    name: str
    qualified_name: str
    is_public: bool
    has_docstring: bool
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ExportInfo:
    from_: str | None
    is_type: bool
    kind: ExportKind
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ImportInfo:
    from_: str
    is_type: bool
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class DeclarationSymbolInfo:
    is_default_export: bool
    is_exported: bool
    kind: DeclarationSymbolKind
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class NamedExportSymbolInfo:
    from_: str | None
    is_type: bool
    name: str
    pos: SourcePosition
    source_name: str


@dataclass(frozen=True, kw_only=True)
class DefaultExportSymbolInfo:
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ImportSourceInfo:
    from_: str
    is_type: bool
    pos: SourcePosition
    level: int


@dataclass(frozen=True, kw_only=True)
class ExtendsClauseInfo:
    name: str
    type_arguments: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class TypeAnnotationInfo:
    base_name: str
    text: str


@dataclass(frozen=True, kw_only=True)
class InterfaceInfo:
    extends: tuple[ExtendsClauseInfo, ...]
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ClassInfo:
    extends: str | None
    implements: tuple[str, ...]
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class ParamInfo:
    name: str
    type_name: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class FunctionInfo:
    name: str
    params: tuple[ParamInfo, ...]
    pos: SourcePosition
    return_type: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class FunctionAnnotationInfo:
    name: str
    qualified_name: str
    is_public: bool
    params: tuple[ParamInfo, ...]
    pos: SourcePosition
    return_type: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class ConstantInfo:
    name: str
    pos: SourcePosition
    type_name: TypeAnnotationInfo | None


@dataclass(frozen=True, kw_only=True)
class TypeAliasInfo:
    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class NonBarrelStatementInfo:
    kind: NonBarrelStatementKind
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class PyFileStructure:
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
