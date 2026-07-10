from __future__ import annotations

import ast

from konpy.python_ast._assignments import (
    _classify_non_barrel_statements,
    _process_assignment,
    _process_type_alias_statement,
)
from konpy.python_ast._classes import _process_class
from konpy.python_ast._collector import _add_module_docstring_target, _Collector
from konpy.python_ast._dunder_all import _collect_all_state
from konpy.python_ast._function_fingerprints import _collect_function_fingerprints
from konpy.python_ast._functions import _process_function
from konpy.python_ast._imports import (
    _collect_typing_aliases,
    _is_type_checking_test,
    _process_import,
    _process_import_from,
    _process_type_checking_if,
)
from konpy.python_ast._string_literals import _collect_string_literals
from konpy.python_ast.structure import PyFileStructure


def parse_file_structure(source: str, file_path: str = "<unknown>") -> PyFileStructure:
    """Parse Python source into a structural summary, or an empty one on a syntax error."""
    try:
        module = ast.parse(source, filename=file_path, type_comments=True)
    except SyntaxError:
        return _empty_file_structure()

    all_state = _collect_all_state(module.body)
    aliases = _collect_typing_aliases(module.body)
    collector = _Collector(all_state=all_state)
    _add_module_docstring_target(module, collector)
    _collect_string_literals(module, collector)
    _collect_function_fingerprints(module, collector)

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
        class_attributes=(),
        constants=(),
        declaration_symbols=(),
        default_export_symbols=(),
        docstring_targets=(),
        exports=(),
        function_annotation_targets=(),
        functions=(),
        function_fingerprints=(),
        import_sources=(),
        imports=(),
        interfaces=(),
        named_export_symbols=(),
        non_barrel_statements=(),
        string_literals=(),
        type_aliases=(),
        all_names=None,
        all_is_dynamic=False,
    )


def _finalize_structure(collector: _Collector) -> PyFileStructure:
    all_names = (
        None
        if collector.all_state.names is None
        else tuple(collector.all_state.names)
    )
    return PyFileStructure(
        classes=tuple(collector.classes),
        class_attributes=tuple(collector.class_attributes),
        constants=tuple(collector.constants),
        declaration_symbols=tuple(collector.declaration_symbols),
        default_export_symbols=tuple(collector.default_export_symbols),
        docstring_targets=tuple(collector.docstring_targets),
        exports=tuple(collector.exports),
        function_annotation_targets=tuple(collector.function_annotation_targets),
        functions=tuple(collector.functions),
        function_fingerprints=tuple(collector.function_fingerprints),
        import_sources=tuple(collector.import_sources),
        imports=tuple(collector.imports),
        interfaces=tuple(collector.interfaces),
        named_export_symbols=tuple(collector.named_export_symbols),
        non_barrel_statements=tuple(collector.non_barrel_statements),
        string_literals=tuple(collector.string_literals),
        type_aliases=tuple(collector.type_aliases),
        all_names=all_names,
        all_is_dynamic=collector.all_state.is_dynamic,
    )


__all__ = ["parse_file_structure"]
