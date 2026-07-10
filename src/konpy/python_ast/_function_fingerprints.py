from __future__ import annotations

import ast

from konpy.python_ast._collector import _Collector, _position
from konpy.python_ast._dunder_all import _is_public
from konpy.python_ast._fingerprint_normalization import _fingerprint_function
from konpy.python_ast.structure import FunctionFingerprintInfo


def _collect_function_fingerprints(module: ast.Module, collector: _Collector) -> None:
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _add_function_fingerprint(
                node,
                collector,
                qualified_name=node.name,
                is_public=_is_public(node.name, collector.all_state),
            )
        elif isinstance(node, ast.ClassDef):
            _collect_method_fingerprints(node, collector)


def _collect_method_fingerprints(node: ast.ClassDef, collector: _Collector) -> None:
    class_is_public = _is_public(node.name, collector.all_state)

    for body_node in node.body:
        if not isinstance(body_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        _add_function_fingerprint(
            body_node,
            collector,
            qualified_name=f"{node.name}.{body_node.name}",
            is_public=class_is_public and not body_node.name.startswith("_"),
        )


def _add_function_fingerprint(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    collector: _Collector,
    *,
    qualified_name: str,
    is_public: bool,
) -> None:
    normalized = _fingerprint_function(node)
    collector.function_fingerprints.append(
        FunctionFingerprintInfo(
            name=node.name,
            qualified_name=qualified_name,
            is_public=is_public,
            pos=_position(node),
            fingerprint=normalized.fingerprint,
            statement_count=normalized.statement_count,
        )
    )


__all__: list[str] = []
