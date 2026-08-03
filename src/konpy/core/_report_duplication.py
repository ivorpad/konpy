"""Duplication-lane assembly for the zero-config report.

Builds the repeated-literal and duplicate-function groups over non-test
structures, tagging groups that repeat by design (generator output, example
snippets, serialization mapping keys) so the renderer can label instead of
flag.
Split out of `konpy.core.report` to keep that module under the project's
per-module line limit.
"""

from __future__ import annotations

from konpy.core._report_model import ReportFunctionGroup, ReportLiteralGroup
from konpy.predicates._duplication_index import (
    _build_duplicate_function_index,
    _build_repeated_literal_index,
    _DuplicateFunctionGroup,
    _StringLiteralOccurrence,
)
from konpy.predicates.restrict_duplicate_functions import DEFAULT_MIN_STATEMENTS
from konpy.predicates.restrict_repeated_literals import (
    DEFAULT_MAX_OCCURRENCES,
    DEFAULT_MIN_LENGTH,
)
from konpy.python_ast.structure import PyFileStructure

# Directory segments whose duplication is self-containment by convention:
# FastAPI-style docs_src/ tutorials and SDK example scripts repeat setup code
# so each snippet stands alone.
_EXAMPLE_SEGMENTS = frozenset({"example", "examples", "docs_src", "samples"})


def _is_example_path(path: str) -> bool:
    segments = path.split("/")[:-1]
    # A bare `docs` dir only reads as documentation at the repo root; a
    # nested one (an SDK's client/docs/ resource modules) is production code.
    if segments and segments[0] == "docs":
        return True
    return any(segment in _EXAMPLE_SEGMENTS for segment in segments)


# Share of occurrences that must sit in mapping-key positions before a group
# reads as protocol keys. Hot keys ("description" in hermes: 572 dict keys,
# 79 `.get()`s, a handful of hasattr/compare uses) never hit 100%.
_MAPPING_KEY_SHARE = 0.9


def _group_label(
    paths: set[str],
    generated: set[str],
    *,
    template: frozenset[str] = frozenset(),
    vendored: frozenset[str] = frozenset(),
    mapping_key_share: float | None = None,
) -> str | None:
    """Tag a duplicate group that repeats by design rather than by accident.

    Single source of truth for group labels, in precedence order: generator
    output (banner-marked or a cookiecutter scaffold -- both render as
    `generator template`), vendored snapshots, example/docs self-containment,
    then (literal groups only, via `mapping_key_share`) serialization mapping
    keys.
    """
    if generated and paths <= generated:
        return "generator template"
    if template and paths <= template:
        return "generator template"
    if vendored and paths <= vendored:
        return "vendored"
    if all(_is_example_path(path) for path in paths):
        return "example/docs code"
    if mapping_key_share is not None and mapping_key_share >= _MAPPING_KEY_SHARE:
        return "mapping keys"
    return None


def _duplication(
    structures: dict[str, PyFileStructure],
    test_paths: set[str],
    generated: set[str],
    *,
    template: frozenset[str] = frozenset(),
    vendored: frozenset[str] = frozenset(),
) -> tuple[tuple[ReportLiteralGroup, ...], tuple[ReportFunctionGroup, ...]]:
    """Build repeated-literal and duplicate-function groups over non-test structures."""
    prod = {path: s for path, s in structures.items() if path not in test_paths}

    literal_index = _build_repeated_literal_index(
        prod,
        min_length=DEFAULT_MIN_LENGTH,
        max_occurrences=DEFAULT_MAX_OCCURRENCES,
        allow=(),
    )
    literal_groups = tuple(
        sorted(
            (
                _literal_group(value, occurrences, generated, template=template, vendored=vendored)
                for value, occurrences in literal_index.items()
            ),
            # Rank by count x length: short schema/dict keys repeat by protocol
            # necessity, while a long literal repeated even a few times is the
            # copy-paste a human would actually extract. Mapping-key-dominated
            # groups rank after everything else.
            key=lambda group: (
                group.label == "mapping keys",
                -(group.occurrences * len(group.value)),
                group.value,
            ),
        )
    )

    function_index = _build_duplicate_function_index(
        prod,
        min_statements=DEFAULT_MIN_STATEMENTS,
        public_only=False,
        allow_names=(),
    )
    function_groups = tuple(
        sorted(
            (
                _function_group(group, generated, template=template, vendored=vendored)
                for group in function_index.values()
            ),
            # Cross-component groups lead (blast radius compounds fastest when
            # a duplicate spans package boundaries); ties break by weighted
            # size (member count x statement count), then name for stability.
            key=lambda group: (
                not group.is_cross_component,
                -(len(group.members) * group.statement_count),
                group.name,
            ),
        )
    )

    return literal_groups, function_groups


def _literal_group(
    value: str,
    occurrences: tuple[_StringLiteralOccurrence, ...],
    generated: set[str],
    *,
    template: frozenset[str] = frozenset(),
    vendored: frozenset[str] = frozenset(),
) -> ReportLiteralGroup:
    mapping_keys = sum(1 for occurrence in occurrences if occurrence.is_mapping_key)
    label = _group_label(
        {occurrence.file_path for occurrence in occurrences},
        generated,
        template=template,
        vendored=vendored,
        mapping_key_share=mapping_keys / len(occurrences),
    )
    return ReportLiteralGroup(
        value=value,
        occurrences=len(occurrences),
        first_path=occurrences[0].file_path,
        first_line=occurrences[0].pos.line,
        label=label,
    )


def _component(path: str) -> str:
    """The top-level unit a path belongs to, for cross-component detection.

    The first path segment, except under a `src`/`lib` layout root where the
    package directory one level down is the real unit (`src/pkg_a/mod.py` ->
    `pkg_a`, `pkg_a/mod.py` -> `pkg_a`).
    """
    segments = path.split("/")
    if segments[0] in ("src", "lib") and len(segments) > 1:
        return segments[1]
    return segments[0]


def _function_group(
    group: _DuplicateFunctionGroup,
    generated: set[str],
    *,
    template: frozenset[str] = frozenset(),
    vendored: frozenset[str] = frozenset(),
) -> ReportFunctionGroup:
    members = (group.canonical, *group.duplicates)
    member_paths = {member.file_path for member in members}
    return ReportFunctionGroup(
        name=group.canonical.name,
        statement_count=group.canonical.statement_count,
        members=tuple((member.file_path, member.pos.line) for member in members),
        label=_group_label(member_paths, generated, template=template, vendored=vendored),
        name_variants=tuple(
            sorted({member.name for member in members} - {group.canonical.name})
        ),
        is_cross_component=len({_component(path) for path in member_paths}) > 1,
    )


__all__: list[str] = []
