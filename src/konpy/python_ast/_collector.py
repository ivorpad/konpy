from __future__ import annotations

import ast
from dataclasses import dataclass, field

from konpy.python_ast._dunder_all import _AllState, _is_public
from konpy.python_ast.structure import (
    ClassInfo,
    ConstantInfo,
    DeclarationSymbolInfo,
    DeclarationSymbolKind,
    DefaultExportSymbolInfo,
    DocstringTargetInfo,
    ExportInfo,
    ExportKind,
    FunctionAnnotationInfo,
    FunctionInfo,
    ImportInfo,
    ImportSourceInfo,
    InterfaceInfo,
    NamedExportSymbolInfo,
    NonBarrelStatementInfo,
    SourcePosition,
    TypeAliasInfo,
)


@dataclass(frozen=True, kw_only=True)
class _ImportBinding:
    bound_name: str
    source_name: str
    from_: str
    level: int
    is_type: bool
    pos: SourcePosition


@dataclass
class _Collector:
    all_state: _AllState
    classes: list[ClassInfo] = field(default_factory=list)
    constants: list[ConstantInfo] = field(default_factory=list)
    declaration_symbols: list[DeclarationSymbolInfo] = field(default_factory=list)
    default_export_symbols: list[DefaultExportSymbolInfo] = field(default_factory=list)
    docstring_targets: list[DocstringTargetInfo] = field(default_factory=list)
    exports: list[ExportInfo] = field(default_factory=list)
    function_annotation_targets: list[FunctionAnnotationInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    import_sources: list[ImportSourceInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    interfaces: list[InterfaceInfo] = field(default_factory=list)
    named_export_symbols: list[NamedExportSymbolInfo] = field(default_factory=list)
    non_barrel_statements: list[NonBarrelStatementInfo] = field(default_factory=list)
    type_aliases: list[TypeAliasInfo] = field(default_factory=list)
    import_bindings: dict[str, _ImportBinding] = field(default_factory=dict)
    _export_keys: set[tuple[str, str | None, bool, ExportKind]] = field(
        default_factory=set
    )
    _named_export_keys: set[tuple[str, str, str | None, bool]] = field(
        default_factory=set
    )


def _position(node: ast.AST) -> SourcePosition:
    return SourcePosition(
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _add_module_docstring_target(module: ast.Module, collector: _Collector) -> None:
    collector.docstring_targets.append(
        DocstringTargetInfo(
            kind="module",
            name="<module>",
            qualified_name="<module>",
            is_public=True,
            has_docstring=ast.get_docstring(module) is not None,
            pos=SourcePosition(line=1, column=1),
        )
    )


def _add_docstring_target(
    collector: _Collector,
    *,
    kind: str,
    name: str,
    qualified_name: str,
    is_public: bool,
    has_docstring: bool,
    pos: SourcePosition,
) -> None:
    collector.docstring_targets.append(
        DocstringTargetInfo(
            kind=kind,
            name=name,
            qualified_name=qualified_name,
            is_public=is_public,
            has_docstring=has_docstring,
            pos=pos,
        )
    )


def _add_export(collector: _Collector, export: ExportInfo) -> None:
    key = (export.name, export.from_, export.is_type, export.kind)
    if key not in collector._export_keys:
        collector._export_keys.add(key)
        collector.exports.append(export)


def _add_named_export_symbol(collector: _Collector, symbol: NamedExportSymbolInfo) -> None:
    key = (symbol.name, symbol.source_name, symbol.from_, symbol.is_type)
    if key not in collector._named_export_keys:
        collector._named_export_keys.add(key)
        collector.named_export_symbols.append(symbol)


def _add_declaration_symbol(
    collector: _Collector,
    *,
    kind: DeclarationSymbolKind,
    name: str,
    pos: SourcePosition,
) -> None:
    collector.declaration_symbols.append(
        DeclarationSymbolInfo(
            is_default_export=False,
            is_exported=_is_public(name, collector.all_state),
            kind=kind,
            name=name,
            pos=pos,
        )
    )
