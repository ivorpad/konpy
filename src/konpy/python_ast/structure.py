from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from konpy.python_ast._dotted_structure import (
    BaseClassRefInfo,
    CallSiteInfo,
    DecoratorInfo,
    ScopedImportInfo,
)
from konpy.python_ast._structure_shared import SourcePosition

ExportKind = Literal["function", "class", "protocol", "const", "type", "re-export"]
DeclarationSymbolKind = Literal["function", "class", "protocol", "type", "const"]
NonBarrelStatementKind = Literal["declaration", "expression"]
DocstringTargetKind = Literal["module", "class", "function"]


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
    """A top-level function, class, protocol, type, or constant declaration."""

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
class AnnotationTextOccurrenceInfo:
    """A normalized annotation text occurrence and its source position."""

    text: str
    pos: SourcePosition
    is_root: bool


@dataclass(frozen=True, kw_only=True)
class TypeAnnotationInfo:
    """A parsed type annotation, with its unsubscripted base name."""

    base_name: str
    text: str
    pos: SourcePosition | None = None
    occurrences: tuple[AnnotationTextOccurrenceInfo, ...] = ()


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
class ClassAttributeInfo:
    """A class-body annotated attribute."""

    name: str
    qualified_name: str
    is_public: bool
    pos: SourcePosition
    type_name: TypeAnnotationInfo


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
    is_public: bool = True


@dataclass(frozen=True, kw_only=True)
class TypeAliasInfo:
    """A `type` statement or `TypeAlias`-annotated assignment."""

    name: str
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class StringLiteralInfo:
    """An eligible repeated-literal candidate in Python source."""

    value: str
    pos: SourcePosition
    # Literal sits in a mapping-key position: a dict-display key
    # (`{"page_token": ...}`), a subscript index (`row["page_token"]`), or the
    # key argument of `.get()`/`.pop()`/`.setdefault()`. Serialization
    # boundaries repeat such keys by protocol necessity, so the report ranks
    # mapping-key-dominated groups last.
    is_mapping_key: bool = False


@dataclass(frozen=True, kw_only=True)
class FunctionFingerprintInfo:
    """A normalized implementation fingerprint for a function or direct method."""

    name: str
    qualified_name: str
    is_public: bool
    pos: SourcePosition
    fingerprint: str
    statement_count: int


@dataclass(frozen=True, kw_only=True)
class NonBarrelStatementInfo:
    """A module-level statement that disqualifies a file from being a barrel."""

    kind: NonBarrelStatementKind
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class PyFileStructure:
    """The full structural summary of a parsed Python source file."""

    classes: tuple[ClassInfo, ...]
    class_attributes: tuple[ClassAttributeInfo, ...]
    constants: tuple[ConstantInfo, ...]
    declaration_symbols: tuple[DeclarationSymbolInfo, ...]
    default_export_symbols: tuple[DefaultExportSymbolInfo, ...]
    docstring_targets: tuple[DocstringTargetInfo, ...]
    exports: tuple[ExportInfo, ...]
    function_annotation_targets: tuple[FunctionAnnotationInfo, ...]
    functions: tuple[FunctionInfo, ...]
    function_fingerprints: tuple[FunctionFingerprintInfo, ...]
    import_sources: tuple[ImportSourceInfo, ...]
    imports: tuple[ImportInfo, ...]
    interfaces: tuple[InterfaceInfo, ...]
    named_export_symbols: tuple[NamedExportSymbolInfo, ...]
    non_barrel_statements: tuple[NonBarrelStatementInfo, ...]
    string_literals: tuple[StringLiteralInfo, ...]
    type_aliases: tuple[TypeAliasInfo, ...]
    decorators: tuple[DecoratorInfo, ...]
    call_sites: tuple[CallSiteInfo, ...]
    base_class_refs: tuple[BaseClassRefInfo, ...]
    scoped_imports: tuple[ScopedImportInfo, ...]
    all_names: tuple[str, ...] | None
    all_is_dynamic: bool


__all__ = [
    "AnnotationTextOccurrenceInfo",
    "BaseClassRefInfo",
    "CallSiteInfo",
    "ClassAttributeInfo",
    "ClassInfo",
    "ConstantInfo",
    "DeclarationSymbolInfo",
    "DeclarationSymbolKind",
    "DecoratorInfo",
    "DefaultExportSymbolInfo",
    "DocstringTargetInfo",
    "DocstringTargetKind",
    "ExportInfo",
    "ExportKind",
    "ExtendsClauseInfo",
    "FunctionAnnotationInfo",
    "FunctionFingerprintInfo",
    "FunctionInfo",
    "ImportInfo",
    "ImportSourceInfo",
    "InterfaceInfo",
    "NamedExportSymbolInfo",
    "NonBarrelStatementInfo",
    "NonBarrelStatementKind",
    "ParamInfo",
    "PyFileStructure",
    "ScopedImportInfo",
    "SourcePosition",
    "StringLiteralInfo",
    "TypeAliasInfo",
    "TypeAnnotationInfo",
]
