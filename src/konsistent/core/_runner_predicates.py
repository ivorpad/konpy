"""Evaluate `must`/`mustNot` predicate blocks against a single matched file."""

from __future__ import annotations

from konsistent.config.schema import MustBlockV1, MustPredicatesV1
from konsistent.core._runner_fix_data import _forbidden_fix_data
from konsistent.core._runner_messages import _format_forbidden_message
from konsistent.core._runner_source_cache import _get_or_parse_file_structure
from konsistent.core._runner_types import _MustNotCheck
from konsistent.core.context import PredicateContext
from konsistent.core.diagnostics import Diagnostic, DiagnosticSeverity, create_diagnostic
from konsistent.core.filesystem import FileSystem
from konsistent.predicates.registry import PredicateRegistry, iter_predicate_items
from konsistent.python_ast.structure import PyFileStructure


def _resolve_block_convention_name(
    *,
    block: MustBlockV1,
    convention_name: str,
) -> str:
    return block.name or convention_name


def _check_must_predicates(
    *,
    must: MustPredicatesV1,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    items = iter_predicate_items(must)
    diagnostics: list[Diagnostic] = []

    structure: PyFileStructure | None = None
    if any(key in predicate_registry.ast_predicates for key, _value in items):
        structure = _get_or_parse_file_structure(
            file_path=context.path,
            file_system=file_system,
            cache=file_structure_cache,
            source_cache=source_cache,
        )

    for key, value in items:
        handler = predicate_registry.handlers.get(key)
        if handler is None:
            continue

        diagnostics.extend(
            handler(
                value,
                context,
                file_system,
                structure,
                convention_name,
                severity,
            )
        )

    return diagnostics


def _build_singleton_predicate(
    *,
    key: str,
    value: object,
    predicate_registry: PredicateRegistry,
) -> MustPredicatesV1:
    return MustPredicatesV1.model_validate(
        {key: value},
        context=predicate_registry.validation_context(),
    )


def _build_must_not_checks(
    *,
    must_not: MustPredicatesV1,
    predicate_registry: PredicateRegistry,
) -> list[_MustNotCheck]:
    checks: list[_MustNotCheck] = []

    for key, value in iter_predicate_items(must_not):
        if isinstance(value, list) and key in predicate_registry.item_level_must_not_predicates:
            for item in value:
                checks.append(
                    _MustNotCheck(
                        key=key,
                        predicate=_build_singleton_predicate(
                            key=key,
                            value=[item],
                            predicate_registry=predicate_registry,
                        ),
                        value=item,
                    )
                )
            continue

        checks.append(
            _MustNotCheck(
                key=key,
                predicate=_build_singleton_predicate(
                    key=key,
                    value=value,
                    predicate_registry=predicate_registry,
                ),
                value=value,
            )
        )

    return checks


def _check_must_not_predicates(
    *,
    must_not: MustPredicatesV1,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for check in _build_must_not_checks(
        must_not=must_not,
        predicate_registry=predicate_registry,
    ):
        normal_diagnostics = _check_must_predicates(
            must=check.predicate,
            convention_name=convention_name,
            context=context,
            file_system=file_system,
            file_structure_cache=file_structure_cache,
            source_cache=source_cache,
            severity=severity,
            predicate_registry=predicate_registry,
        )
        if normal_diagnostics:
            continue

        fix_data = _forbidden_fix_data(
            key=check.key,
            value=check.value,
            context=context,
            file_system=file_system,
            file_structure_cache=file_structure_cache,
            source_cache=source_cache,
        )

        diagnostics.append(
            create_diagnostic(
                file_path=context.path,
                predicate_name=f"mustNot.{check.key}",
                message=_format_forbidden_message(
                    key=check.key,
                    value=check.value,
                    context=context,
                    predicate_registry=predicate_registry,
                ),
                convention_name=convention_name,
                severity=severity,
                expected=fix_data.expected,
                found=fix_data.found,
                fix_hint=fix_data.fix_hint,
                line=fix_data.line,
                column=fix_data.column,
            )
        )

    return diagnostics


def _check_predicates(
    *,
    must: MustPredicatesV1 | None,
    must_not: MustPredicatesV1 | None,
    convention_name: str | None,
    context: PredicateContext,
    file_system: FileSystem,
    file_structure_cache: dict[str, PyFileStructure],
    source_cache: dict[str, str],
    severity: DiagnosticSeverity | None,
    predicate_registry: PredicateRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if must is not None:
        diagnostics.extend(
            _check_must_predicates(
                must=must,
                convention_name=convention_name,
                context=context,
                file_system=file_system,
                file_structure_cache=file_structure_cache,
                source_cache=source_cache,
                severity=severity,
                predicate_registry=predicate_registry,
            )
        )

    if must_not is not None:
        diagnostics.extend(
            _check_must_not_predicates(
                must_not=must_not,
                convention_name=convention_name,
                context=context,
                file_system=file_system,
                file_structure_cache=file_structure_cache,
                source_cache=source_cache,
                severity=severity,
                predicate_registry=predicate_registry,
            )
        )

    return diagnostics
