from __future__ import annotations

import ast
from dataclasses import dataclass, field

from konsistent.python_ast.structure import (
    ClassInfo,
    ConstantInfo,
    DeclarationSymbolInfo,
    DeclarationSymbolKind,
    DefaultExportSymbolInfo,
    DocstringTargetInfo,
    ExportInfo,
    ExportKind,
    ExtendsClauseInfo,
    FunctionAnnotationInfo,
    FunctionInfo,
    ImportInfo,
    ImportSourceInfo,
    InterfaceInfo,
    NamedExportSymbolInfo,
    NonBarrelStatementInfo,
    ParamInfo,
    PyFileStructure,
    SourcePosition,
    TypeAliasInfo,
    TypeAnnotationInfo,
)


@dataclass
class _AllState:
    names: list[str] | None = None
    is_dynamic: bool = False


@dataclass(frozen=True, kw_only=True)
class _ImportBinding:
    bound_name: str
    source_name: str
    from_: str
    level: int
    is_type: bool
    pos: SourcePosition


@dataclass(frozen=True, kw_only=True)
class _TypingAliases:
    type_checking_names: set[str]
    typing_module_names: set[str]


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


def parse_file_structure(source: str, file_path: str = "<unknown>") -> PyFileStructure:
    try:
        module = ast.parse(source, filename=file_path, type_comments=True)
    except SyntaxError:
        return _empty_file_structure()

    all_state = _collect_all_state(module.body)
    aliases = _collect_typing_aliases(module.body)
    collector = _Collector(all_state=all_state)
    _add_module_docstring_target(module, collector)

    for node in module.body:
        if isinstance(node, ast.Import):
            _process_import(node, collector, is_type=False)
        elif isinstance(node, ast.ImportFrom):
            _process_import_from(node, collector, is_type=False)
        elif isinstance(node, ast.If) and _is_type_checking_test(node.test, aliases):
            _process_type_checking_if(node, collector)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _process_function(node, collector)
        elif isinstance(node, ast.ClassDef):
            _process_class(node, collector)
        elif isinstance(node, ast.TypeAlias):
            _process_type_alias_statement(node, collector)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            _process_assignment(node, collector)

    _classify_non_barrel_statements(module.body, collector, aliases)
    return _finalize_structure(collector)


def _empty_file_structure() -> PyFileStructure:
    return PyFileStructure(
        classes=(),
        constants=(),
        declaration_symbols=(),
        default_export_symbols=(),
        docstring_targets=(),
        exports=(),
        function_annotation_targets=(),
        functions=(),
        import_sources=(),
        imports=(),
        interfaces=(),
        named_export_symbols=(),
        non_barrel_statements=(),
        type_aliases=(),
        all_names=None,
        all_is_dynamic=False,
    )


def _position(node: ast.AST) -> SourcePosition:
    return SourcePosition(
        line=getattr(node, "lineno", 1),
        column=getattr(node, "col_offset", 0) + 1,
    )


def _written_from_specifier(*, module: str | None, level: int) -> str:
    if level <= 0:
        return module or ""
    dots = "." * level
    return f"{dots}{module}" if module else dots


def _finalize_structure(collector: _Collector) -> PyFileStructure:
    all_names = (
        None
        if collector.all_state.names is None
        else tuple(collector.all_state.names)
    )
    return PyFileStructure(
        classes=tuple(collector.classes),
        constants=tuple(collector.constants),
        declaration_symbols=tuple(collector.declaration_symbols),
        default_export_symbols=tuple(collector.default_export_symbols),
        docstring_targets=tuple(collector.docstring_targets),
        exports=tuple(collector.exports),
        function_annotation_targets=tuple(collector.function_annotation_targets),
        functions=tuple(collector.functions),
        import_sources=tuple(collector.import_sources),
        imports=tuple(collector.imports),
        interfaces=tuple(collector.interfaces),
        named_export_symbols=tuple(collector.named_export_symbols),
        non_barrel_statements=tuple(collector.non_barrel_statements),
        type_aliases=tuple(collector.type_aliases),
        all_names=all_names,
        all_is_dynamic=collector.all_state.is_dynamic,
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


def _add_function_coverage_target(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    collector: _Collector,
    *,
    qualified_name: str,
    is_public: bool,
    skip_first_self_or_cls: bool,
) -> None:
    pos = _position(node)
    _add_docstring_target(
        collector,
        kind="function",
        name=node.name,
        qualified_name=qualified_name,
        is_public=is_public,
        has_docstring=ast.get_docstring(node) is not None,
        pos=pos,
    )
    collector.function_annotation_targets.append(
        FunctionAnnotationInfo(
            name=node.name,
            qualified_name=qualified_name,
            is_public=is_public,
            params=_function_annotation_params(
                node.args,
                skip_first_self_or_cls=skip_first_self_or_cls,
            ),
            pos=pos,
            return_type=_annotation_info(node.returns),
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


def _collect_all_state(body: list[ast.stmt]) -> _AllState:
    state = _AllState()
    for node in body:
        if not _is_all_statement(node):
            continue
        values = _all_statement_literal_values(node)
        if values is None:
            state.names = None
            state.is_dynamic = True
            continue
        if state.is_dynamic:
            continue
        if state.names is None:
            state.names = []
        _merge_all_names(state.names, values)
    return state


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_string_sequence(node: ast.AST | None) -> list[str] | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values: list[str] = []
    for element in node.elts:
        value = _literal_string(element)
        if value is None:
            return None
        values.append(value)
    return values


def _merge_all_names(existing: list[str], incoming: list[str]) -> None:
    for name in incoming:
        if name not in existing:
            existing.append(name)


def _is_all_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _is_all_assign(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return len(node.targets) == 1 and _is_all_name(node.targets[0])
    if isinstance(node, ast.AnnAssign):
        return _is_all_name(node.target)
    return False


def _is_all_augassign(node: ast.stmt) -> bool:
    return isinstance(node, ast.AugAssign) and _is_all_name(node.target)


def _is_all_mutation_expr(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr in {"append", "extend"}
        and _is_all_name(node.value.func.value)
    )


def _is_all_statement(node: ast.stmt) -> bool:
    return _is_all_assign(node) or _is_all_augassign(node) or _is_all_mutation_expr(node)


def _all_statement_literal_values(node: ast.stmt) -> list[str] | None:
    if isinstance(node, ast.Assign) and _is_all_assign(node):
        return _literal_string_sequence(node.value)
    if isinstance(node, ast.AnnAssign) and _is_all_assign(node):
        return _literal_string_sequence(node.value) if node.value is not None else None
    if isinstance(node, ast.AugAssign) and _is_all_augassign(node):
        return _literal_string_sequence(node.value)
    if not _is_all_mutation_expr(node):
        return None

    call = node.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr == "append" and len(call.args) == 1:
        value = _literal_string(call.args[0])
        return [value] if value is not None else None
    if call.func.attr == "extend" and len(call.args) == 1:
        return _literal_string_sequence(call.args[0])
    return None


def _is_allowed_all_statement(node: ast.stmt) -> bool:
    return _is_all_statement(node) and _all_statement_literal_values(node) is not None


def _target_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _is_public(name: str, all_state: _AllState) -> bool:
    if all_state.names is not None:
        return name in all_state.names
    return not name.startswith("_")


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


def _annotation_info(annotation: ast.expr | None) -> TypeAnnotationInfo | None:
    if annotation is None:
        return None
    text = ast.unparse(annotation)
    return TypeAnnotationInfo(base_name=_annotation_base_name(annotation), text=text)


def _annotation_base_name(annotation: ast.expr) -> str:
    if isinstance(annotation, ast.Subscript):
        return ast.unparse(annotation.value)
    return ast.unparse(annotation)


def _is_final_annotation(annotation: ast.expr | None) -> bool:
    return annotation is not None and _annotation_base_name(annotation) in {
        "Final",
        "typing.Final",
    }


def _is_type_alias_annotation(annotation: ast.expr | None) -> bool:
    return annotation is not None and _annotation_base_name(annotation) in {
        "TypeAlias",
        "typing.TypeAlias",
    }


def _expr_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{_expr_name(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Subscript):
        return _expr_name(expr.value)
    return ast.unparse(expr)


def _subscript_type_arguments(expr: ast.Subscript) -> tuple[str, ...]:
    if isinstance(expr.slice, ast.Tuple):
        return tuple(ast.unparse(element) for element in expr.slice.elts)
    return (ast.unparse(expr.slice),)


def _process_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    collector: _Collector,
) -> None:
    pos = _position(node)
    collector.functions.append(
        FunctionInfo(
            name=node.name,
            params=_function_params(node.args),
            pos=pos,
            return_type=_annotation_info(node.returns),
        )
    )
    _add_function_coverage_target(
        node,
        collector,
        qualified_name=node.name,
        is_public=_is_public(node.name, collector.all_state),
        skip_first_self_or_cls=False,
    )
    _add_declaration_symbol(collector, kind="function", name=node.name, pos=pos)
    if _is_public(node.name, collector.all_state):
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=False,
                kind="function",
                name=node.name,
                pos=pos,
            ),
        )


def _function_params(args: ast.arguments) -> tuple[ParamInfo, ...]:
    return tuple(
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in [*args.posonlyargs, *args.args]
    )


def _function_annotation_params(
    args: ast.arguments,
    *,
    skip_first_self_or_cls: bool,
) -> tuple[ParamInfo, ...]:
    params = [
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in [*args.posonlyargs, *args.args]
    ]

    if args.vararg is not None:
        params.append(
            ParamInfo(
                name=args.vararg.arg,
                type_name=_annotation_info(args.vararg.annotation),
            )
        )

    params.extend(
        ParamInfo(name=arg.arg, type_name=_annotation_info(arg.annotation))
        for arg in args.kwonlyargs
    )

    if args.kwarg is not None:
        params.append(
            ParamInfo(
                name=args.kwarg.arg,
                type_name=_annotation_info(args.kwarg.annotation),
            )
        )

    if skip_first_self_or_cls and params and params[0].name in {"self", "cls"}:
        params = params[1:]

    return tuple(params)


def _process_class(node: ast.ClassDef, collector: _Collector) -> None:
    pos = _position(node)
    is_protocol = _is_protocol_or_abc_class(node)
    symbol_kind: DeclarationSymbolKind = "protocol" if is_protocol else "class"
    export_kind: ExportKind = "protocol" if is_protocol else "class"
    extends, implements = _class_extends_and_implements(node)
    is_public = _is_public(node.name, collector.all_state)

    collector.classes.append(
        ClassInfo(extends=extends, implements=implements, name=node.name, pos=pos)
    )
    _add_docstring_target(
        collector,
        kind="class",
        name=node.name,
        qualified_name=node.name,
        is_public=is_public,
        has_docstring=ast.get_docstring(node) is not None,
        pos=pos,
    )
    _process_class_methods(node, collector, class_is_public=is_public)

    if is_protocol:
        collector.interfaces.append(
            InterfaceInfo(extends=_class_base_infos(node), name=node.name, pos=pos)
        )

    _add_declaration_symbol(collector, kind=symbol_kind, name=node.name, pos=pos)
    if is_public:
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=is_protocol,
                kind=export_kind,
                name=node.name,
                pos=pos,
            ),
        )


def _process_class_methods(
    node: ast.ClassDef,
    collector: _Collector,
    *,
    class_is_public: bool,
) -> None:
    for body_node in node.body:
        if not isinstance(body_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        _add_function_coverage_target(
            body_node,
            collector,
            qualified_name=f"{node.name}.{body_node.name}",
            is_public=class_is_public and not body_node.name.startswith("_"),
            skip_first_self_or_cls=True,
        )


def _base_expr_name(expr: ast.expr) -> str:
    return _expr_name(expr)


def _base_type_arguments(expr: ast.expr) -> tuple[str, ...]:
    return _subscript_type_arguments(expr) if isinstance(expr, ast.Subscript) else ()


def _is_protocol_or_abc_marker(name: str) -> bool:
    return name in {"Protocol", "typing.Protocol", "ABC", "abc.ABC"}


def _is_abc_metaclass(node: ast.ClassDef) -> bool:
    return any(
        keyword.arg == "metaclass"
        and _expr_name(keyword.value) in {"ABCMeta", "abc.ABCMeta"}
        for keyword in node.keywords
    )


def _is_protocol_or_abc_class(node: ast.ClassDef) -> bool:
    return _is_abc_metaclass(node) or any(
        _is_protocol_or_abc_marker(_base_expr_name(base)) for base in node.bases
    )


def _class_base_infos(node: ast.ClassDef) -> tuple[ExtendsClauseInfo, ...]:
    infos: list[ExtendsClauseInfo] = []
    for base in node.bases:
        name = _base_expr_name(base)
        if _is_protocol_or_abc_marker(name):
            continue
        infos.append(
            ExtendsClauseInfo(name=name, type_arguments=_base_type_arguments(base))
        )
    return tuple(infos)


def _class_extends_and_implements(
    node: ast.ClassDef,
) -> tuple[str | None, tuple[str, ...]]:
    non_marker_bases = [
        _base_expr_name(base)
        for base in node.bases
        if not _is_protocol_or_abc_marker(_base_expr_name(base))
    ]
    return (
        non_marker_bases[0] if non_marker_bases else None,
        tuple(non_marker_bases[1:]),
    )


def _process_assignment(node: ast.Assign | ast.AnnAssign, collector: _Collector) -> None:
    if _is_all_statement(node):
        return
    if isinstance(node, ast.AnnAssign) and _process_ann_assign_type_alias(
        node,
        collector,
    ):
        return
    if _process_assignment_reexport(node, collector):
        return
    _process_const_assignment(node, collector)


def _process_type_alias_statement(node: ast.TypeAlias, collector: _Collector) -> None:
    name = _target_name(node.name)
    if name is None:
        return
    pos = _position(node.name)
    collector.type_aliases.append(TypeAliasInfo(name=name, pos=pos))
    _add_declaration_symbol(collector, kind="type", name=name, pos=pos)
    if _is_public(name, collector.all_state):
        _add_export(
            collector, ExportInfo(from_=None, is_type=True, kind="type", name=name, pos=pos)
        )


def _process_ann_assign_type_alias(node: ast.AnnAssign, collector: _Collector) -> bool:
    if not _is_type_alias_annotation(node.annotation):
        return False
    name = _target_name(node.target)
    if name is None:
        return True
    pos = _position(node.target)
    collector.type_aliases.append(TypeAliasInfo(name=name, pos=pos))
    _add_declaration_symbol(collector, kind="type", name=name, pos=pos)
    if _is_public(name, collector.all_state):
        _add_export(
            collector, ExportInfo(from_=None, is_type=True, kind="type", name=name, pos=pos)
        )
    return True


def _process_assignment_reexport(
    node: ast.Assign | ast.AnnAssign,
    collector: _Collector,
) -> bool:
    target = _single_name_assignment_target(node)
    value = _assignment_value(node)
    if target is None or not isinstance(value, ast.Name):
        return False
    binding = collector.import_bindings.get(value.id)
    if binding is None or not _is_public(target.id, collector.all_state):
        return False

    pos = _position(target)
    _add_export(
        collector,
        ExportInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            kind="re-export",
            name=target.id,
            pos=pos,
        ),
    )
    _add_named_export_symbol(
        collector,
        NamedExportSymbolInfo(
            from_=binding.from_,
            is_type=binding.is_type,
            name=target.id,
            pos=pos,
            source_name=binding.source_name,
        ),
    )
    return True


def _process_const_assignment(
    node: ast.Assign | ast.AnnAssign,
    collector: _Collector,
) -> None:
    target = _single_name_assignment_target(node)
    if target is None:
        return
    annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
    if not (_is_uppercase_constant_name(target.id) or _is_final_annotation(annotation)):
        return
    pos = _position(target)
    collector.constants.append(
        ConstantInfo(name=target.id, pos=pos, type_name=_annotation_info(annotation))
    )
    _add_declaration_symbol(collector, kind="const", name=target.id, pos=pos)
    if _is_public(target.id, collector.all_state):
        _add_export(
            collector,
            ExportInfo(
                from_=None,
                is_type=False,
                kind="const",
                name=target.id,
                pos=pos,
            ),
        )


def _is_uppercase_constant_name(name: str) -> bool:
    return name.upper() == name and any(char.isalpha() for char in name)


def _single_name_assignment_target(node: ast.Assign | ast.AnnAssign) -> ast.Name | None:
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1:
            return None
        return node.targets[0] if isinstance(node.targets[0], ast.Name) else None
    return node.target if isinstance(node.target, ast.Name) else None


def _assignment_value(node: ast.Assign | ast.AnnAssign) -> ast.expr | None:
    return node.value


def _classify_non_barrel_statements(
    body: list[ast.stmt],
    collector: _Collector,
    aliases: _TypingAliases,
) -> None:
    for index, node in enumerate(body):
        entry = _classify_statement(
            node,
            index=index,
            collector=collector,
            aliases=aliases,
        )
        if entry is not None:
            collector.non_barrel_statements.append(entry)


def _classify_statement(
    node: ast.stmt,
    *,
    index: int,
    collector: _Collector,
    aliases: _TypingAliases,
) -> NonBarrelStatementInfo | None:
    if _is_module_docstring(node, index=index):
        return None
    if isinstance(node, ast.Import | ast.ImportFrom):
        return None
    if _is_allowed_all_statement(node):
        return None
    if isinstance(node, ast.If) and _is_type_checking_test(node.test, aliases):
        return None
    if _is_allowed_reexport_assignment(node, collector):
        return None
    if isinstance(
        node,
        ast.FunctionDef
        | ast.AsyncFunctionDef
        | ast.ClassDef
        | ast.Assign
        | ast.AnnAssign
        | ast.TypeAlias,
    ):
        return NonBarrelStatementInfo(kind="declaration", pos=_position(node))
    return NonBarrelStatementInfo(kind="expression", pos=_position(node))


def _is_module_docstring(node: ast.stmt, *, index: int) -> bool:
    return (
        index == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_allowed_reexport_assignment(node: ast.stmt, collector: _Collector) -> bool:
    if not isinstance(node, ast.Assign | ast.AnnAssign):
        return False
    target = _single_name_assignment_target(node)
    value = _assignment_value(node)
    return (
        target is not None
        and isinstance(value, ast.Name)
        and value.id in collector.import_bindings
        and _is_public(target.id, collector.all_state)
    )


__all__ = ["parse_file_structure"]
