from __future__ import annotations

import ast
from dataclasses import dataclass

from konpy.python_ast._collector import (
    _add_export,
    _add_named_export_symbol,
    _Collector,
    _ImportBinding,
    _position,
)
from konpy.python_ast._dunder_all import _is_public
from konpy.python_ast.structure import (
    ExportInfo,
    ImportInfo,
    ImportSourceInfo,
    NamedExportSymbolInfo,
    SourcePosition,
)


@dataclass(frozen=True, kw_only=True)
class _TypingAliases:
    type_checking_names: set[str]
    typing_module_names: set[str]


def _written_from_specifier(*, module: str | None, level: int) -> str:
    if level <= 0:
        return module or ""
    dots = "." * level
    return f"{dots}{module}" if module else dots


def _collect_typing_aliases(body: list[ast.stmt]) -> _TypingAliases:
    type_checking_names = {"TYPE_CHECKING"}
    typing_module_names = {"typing"}

    for node in body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "typing":
                    typing_module_names.add(alias.asname or "typing")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "typing"
            and node.level == 0
        ):
            for alias in node.names:
                if alias.name == "TYPE_CHECKING":
                    type_checking_names.add(alias.asname or alias.name)

    return _TypingAliases(
        type_checking_names=type_checking_names,
        typing_module_names=typing_module_names,
    )


def _is_type_checking_test(test: ast.expr, aliases: _TypingAliases) -> bool:
    if isinstance(test, ast.Name):
        return test.id in aliases.type_checking_names
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id in aliases.typing_module_names
    )


def _process_type_checking_if(node: ast.If, collector: _Collector) -> None:
    for body_node in node.body:
        if isinstance(body_node, ast.Import):
            _process_import(body_node, collector, is_type=True)
        elif isinstance(body_node, ast.ImportFrom):
            _process_import_from(body_node, collector, is_type=True)

    for else_node in node.orelse:
        if isinstance(else_node, ast.Import):
            _process_import(else_node, collector, is_type=False)
        elif isinstance(else_node, ast.ImportFrom):
            _process_import_from(else_node, collector, is_type=False)


def _process_import(node: ast.Import, collector: _Collector, *, is_type: bool) -> None:
    pos = _position(node)
    for alias in node.names:
        bound_name = alias.asname or alias.name.split(".", 1)[0]
        collector.import_sources.append(
            ImportSourceInfo(from_=alias.name, is_type=is_type, level=0, pos=pos)
        )
        collector.imports.append(
            ImportInfo(from_=alias.name, is_type=is_type, name=bound_name, pos=pos)
        )
        _record_import_binding(
            collector,
            bound_name=bound_name,
            source_name=alias.name.split(".", 1)[0],
            from_=alias.name,
            level=0,
            is_type=is_type,
            pos=pos,
        )
        _maybe_add_import_reexport(collector, bound_name)


def _process_import_from(
    node: ast.ImportFrom,
    collector: _Collector,
    *,
    is_type: bool,
) -> None:
    pos = _position(node)
    from_ = _written_from_specifier(module=node.module, level=node.level)

    collector.import_sources.append(
        ImportSourceInfo(from_=from_, is_type=is_type, level=node.level, pos=pos)
    )

    for alias in node.names:
        bound_name = alias.asname or alias.name
        collector.imports.append(
            ImportInfo(from_=from_, is_type=is_type, name=bound_name, pos=pos)
        )
        _record_import_binding(
            collector,
            bound_name=bound_name,
            source_name=alias.name,
            from_=from_,
            level=node.level,
            is_type=is_type,
            pos=pos,
        )
        _maybe_add_import_reexport(collector, bound_name)


def _record_import_binding(
    collector: _Collector,
    *,
    bound_name: str,
    source_name: str,
    from_: str,
    level: int,
    is_type: bool,
    pos: SourcePosition,
) -> None:
    collector.import_bindings[bound_name] = _ImportBinding(
        bound_name=bound_name,
        source_name=source_name,
        from_=from_,
        level=level,
        is_type=is_type,
        pos=pos,
    )


def _maybe_add_import_reexport(collector: _Collector, bound_name: str) -> None:
    binding = collector.import_bindings[bound_name]
    if not _is_public(bound_name, collector.all_state):
        return
    _add_export(
        collector,
        ExportInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            kind="re-export",
            name=bound_name,
            pos=binding.pos,
        ),
    )
    _add_named_export_symbol(
        collector,
        NamedExportSymbolInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            name=bound_name,
            pos=binding.pos,
            source_name=binding.source_name,
        ),
    )
