from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from konpy.core._suppressions_parsing import (
    HYGIENE_CONVENTION_NAME,
    SuppressionComment,
    SuppressionKind,
    _hygiene_diagnostic,
)
from konpy.core.diagnostics import Diagnostic

UsageKey = tuple[str, int, SuppressionKind, str]


@dataclass(frozen=True, kw_only=True)
class AppliedSuppression:
    """A suppression comment matched against the diagnostic it silences."""

    file_path: str
    line: int
    kind: SuppressionKind
    rule: str
    reason: str | None


@dataclass(frozen=True, kw_only=True)
class SuppressedDiagnostic:
    """A diagnostic paired with the suppression comment that silenced it."""

    diagnostic: Diagnostic
    suppression: AppliedSuppression


@dataclass(frozen=True, kw_only=True)
class SuppressionFilterResult:
    """The outcome of filtering a diagnostic list through known suppressions."""

    diagnostics: list[Diagnostic]
    suppressed: list[SuppressedDiagnostic]
    hygiene_diagnostics: list[Diagnostic]


@dataclass(frozen=True, kw_only=True)
class _MatchedSuppression:
    applied: AppliedSuppression
    usage_key: UsageKey


def filter_suppressed_diagnostics(
    *,
    diagnostics: list[Diagnostic],
    suppressions_by_file: Mapping[str, list[SuppressionComment]],
    parse_diagnostics: list[Diagnostic],
    known_rule_names: set[str],
    report_hygiene: bool,
) -> SuppressionFilterResult:
    """Split diagnostics into unsuppressed/suppressed and collect hygiene warnings.

    A diagnostic is suppressed when a matching same-line, previous-line, or
    file-level `ignore`/`ignore-file` comment names its convention. When
    `report_hygiene` is true, unused and unknown suppression comments (plus
    any `parse_diagnostics` from parsing) are surfaced as hygiene diagnostics.
    """
    visible: list[Diagnostic] = []
    suppressed: list[SuppressedDiagnostic] = []
    used_suppressions: set[UsageKey] = set()

    for diagnostic in diagnostics:
        match = _find_matching_suppression(
            diagnostic=diagnostic,
            suppressions=suppressions_by_file.get(diagnostic.file_path, []),
            known_rule_names=known_rule_names,
        )
        if match is None:
            visible.append(diagnostic)
            continue

        used_suppressions.add(match.usage_key)
        suppressed.append(
            SuppressedDiagnostic(
                diagnostic=diagnostic,
                suppression=match.applied,
            )
        )

    hygiene_diagnostics: list[Diagnostic] = []
    if report_hygiene:
        hygiene_diagnostics.extend(parse_diagnostics)
        hygiene_diagnostics.extend(
            _collect_unused_and_unknown_suppression_diagnostics(
                suppressions_by_file=suppressions_by_file,
                known_rule_names=known_rule_names,
                used_suppressions=used_suppressions,
            )
        )

    return SuppressionFilterResult(
        diagnostics=visible,
        suppressed=suppressed,
        hygiene_diagnostics=hygiene_diagnostics,
    )


def _find_matching_suppression(
    *,
    diagnostic: Diagnostic,
    suppressions: list[SuppressionComment],
    known_rule_names: set[str],
) -> _MatchedSuppression | None:
    rule = diagnostic.convention_name
    if rule is None:
        return None
    if rule == HYGIENE_CONVENTION_NAME:
        return None
    if rule not in known_rule_names:
        return None

    same_line = _find_line_suppression(
        diagnostic=diagnostic,
        suppressions=suppressions,
        rule=rule,
        offset=0,
    )
    if same_line is not None:
        return same_line

    previous_line = _find_line_suppression(
        diagnostic=diagnostic,
        suppressions=suppressions,
        rule=rule,
        offset=-1,
    )
    if previous_line is not None:
        return previous_line

    return _find_file_suppression(
        diagnostic=diagnostic,
        suppressions=suppressions,
        rule=rule,
    )


def _find_line_suppression(
    *,
    diagnostic: Diagnostic,
    suppressions: list[SuppressionComment],
    rule: str,
    offset: int,
) -> _MatchedSuppression | None:
    if diagnostic.line is None:
        return None

    expected_line = diagnostic.line + offset
    for suppression in suppressions:
        if suppression.kind != "ignore":
            continue
        if suppression.line != expected_line:
            continue
        if rule not in suppression.rules:
            continue
        return _matched_suppression(suppression=suppression, rule=rule)

    return None


def _find_file_suppression(
    *,
    diagnostic: Diagnostic,
    suppressions: list[SuppressionComment],
    rule: str,
) -> _MatchedSuppression | None:
    del diagnostic

    for suppression in suppressions:
        if suppression.kind != "ignore-file":
            continue
        if rule not in suppression.rules:
            continue
        return _matched_suppression(suppression=suppression, rule=rule)

    return None


def _matched_suppression(
    *,
    suppression: SuppressionComment,
    rule: str,
) -> _MatchedSuppression:
    return _MatchedSuppression(
        applied=AppliedSuppression(
            file_path=suppression.file_path,
            line=suppression.line,
            kind=suppression.kind,
            rule=rule,
            reason=suppression.reason,
        ),
        usage_key=_usage_key(suppression=suppression, rule=rule),
    )


def _collect_unused_and_unknown_suppression_diagnostics(
    *,
    suppressions_by_file: Mapping[str, list[SuppressionComment]],
    known_rule_names: set[str],
    used_suppressions: set[UsageKey],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for suppressions in suppressions_by_file.values():
        for suppression in suppressions:
            for rule in suppression.rules:
                if rule not in known_rule_names:
                    diagnostics.append(
                        _hygiene_diagnostic(
                            file_path=suppression.file_path,
                            line=suppression.line,
                            message=f'Unknown suppression rule "{rule}"',
                        )
                    )
                    continue

                if _usage_key(suppression=suppression, rule=rule) in used_suppressions:
                    continue

                diagnostics.append(
                    _hygiene_diagnostic(
                        file_path=suppression.file_path,
                        line=suppression.line,
                        message=f'Unused suppression for "{rule}"',
                    )
                )

    return diagnostics


def _usage_key(
    *,
    suppression: SuppressionComment,
    rule: str,
) -> UsageKey:
    return (
        suppression.file_path,
        suppression.line,
        suppression.kind,
        rule,
    )


__all__ = [
    "AppliedSuppression",
    "SuppressedDiagnostic",
    "SuppressionFilterResult",
    "filter_suppressed_diagnostics",
]
