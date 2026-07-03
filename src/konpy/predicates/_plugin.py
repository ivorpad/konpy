from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from konpy.core.context import PredicateContext
from konpy.core.diagnostics import Diagnostic, DiagnosticSeverity
from konpy.core.filesystem import FileSystem
from konpy.plugin import PredicatePlugin
from konpy.predicates._handlers import PredicateHandler
from konpy.python_ast.structure import PyFileStructure

ForbiddenMessageProvider = Callable[[object, PredicateContext], str]


@dataclass(frozen=True, kw_only=True)
class PluginOrigin:
    """The installed distribution and entry point a plugin predicate came from."""

    distribution_name: str
    entry_point_name: str


def wrap_plugin_handler(plugin: PredicatePlugin) -> PredicateHandler:
    """Adapt a plugin's PredicatePlugin.handler to the built-in PredicateHandler shape."""

    def wrapped(
        value: object,
        context: PredicateContext,
        file_system: FileSystem,
        structure: PyFileStructure | None,
        convention_name: str | None,
        severity: DiagnosticSeverity | None,
    ) -> list[Diagnostic]:
        del file_system
        return plugin.handler(
            expected=value,
            context=context,
            structure=structure,
            convention_name=convention_name,
            severity=severity,
        )

    return wrapped
