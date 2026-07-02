from __future__ import annotations

import io
import re
import tokenize as py_tokenize
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from konsistent.core.diagnostics import Diagnostic, create_diagnostic

SuppressionKind = Literal["ignore", "ignore-file"]

_RULE_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_KONSISTENT_PREFIX_RE = re.compile(r"^#\s*konsistent:")
_SUPPRESSION_RE = re.compile(
    r"^#\s*konsistent:\s*"
    r"(?P<kind>ignore|ignore-file)"
    r"\[(?P<rules>[^\]]*)\]"
    r"(?P<tail>.*)$"
)

HYGIENE_CONVENTION_NAME = "suppressions"


@dataclass(frozen=True, kw_only=True)
class SuppressionComment:
    file_path: str
    line: int
    kind: SuppressionKind
    rules: tuple[str, ...]
    reason: str | None
    raw: str


@dataclass(frozen=True, kw_only=True)
class SuppressionParseResult:
    suppressions: list[SuppressionComment]
    diagnostics: list[Diagnostic]


@dataclass(frozen=True, kw_only=True)
class AppliedSuppression:
    file_path: str
    line: int
    kind: SuppressionKind
    rule: str
    reason: str | None


@dataclass(frozen=True, kw_only=True)
class SuppressedDiagnostic:
    diagnostic: Diagnostic
    suppression: AppliedSuppression


@dataclass(frozen=True, kw_only=True)
class SuppressionFilterResult:
    diagnostics: list[Diagnostic]
    suppressed: list[SuppressedDiagnostic]
    hygiene_diagnostics: list[Diagnostic]


UsageKey = tuple[str, int, SuppressionKind, str]


@dataclass(frozen=True, kw_only=True)
class _MatchedSuppression:
    applied: AppliedSuppression
    usage_key: UsageKey


def parse_suppressions_for_source(
    *,
    file_path: str,
    source: str,
) -> SuppressionParseResult:
    suppressions: list[SuppressionComment] = []
    diagnostics: list[Diagnostic] = []
    first_code_line = _first_code_line(source)

    for line, comment_text in _iter_comment_tokens(source):
        parsed, parse_diagnostics = _parse_suppression_comment(
            file_path=file_path,
            line=line,
            comment_text=comment_text,
        )
        diagnostics.extend(parse_diagnostics)

        if parsed is None:
            continue

        if parsed.kind == "ignore-file" and _is_after_first_code_line(
            suppression_line=parsed.line,
            first_code_line=first_code_line,
        ):
            diagnostics.extend(
                _invalid_file_level_placement_diagnostics(
                    suppression=parsed,
                )
            )
            continue

        suppressions.append(parsed)

    return SuppressionParseResult(
        suppressions=suppressions,
        diagnostics=diagnostics,
    )


def filter_suppressed_diagnostics(
    *,
    diagnostics: list[Diagnostic],
    suppressions_by_file: Mapping[str, list[SuppressionComment]],
    parse_diagnostics: list[Diagnostic],
    known_rule_names: set[str],
    report_hygiene: bool,
) -> SuppressionFilterResult:
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


def _iter_comment_tokens(source: str) -> list[tuple[int, str]]:
    try:
        tokens = py_tokenize.generate_tokens(io.StringIO(source).readline)
        return [
            (token.start[0], token.string)
            for token in tokens
            if token.type == py_tokenize.COMMENT
        ]
    except (IndentationError, py_tokenize.TokenError):
        return _iter_comment_tokens_fallback(source)


def _iter_comment_tokens_fallback(source: str) -> list[tuple[int, str]]:
    comments: list[tuple[int, str]] = []
    for index, line in enumerate(source.splitlines(), start=1):
        marker_index = line.find("#")
        if marker_index < 0:
            continue
        comments.append((index, line[marker_index:]))
    return comments


def _parse_suppression_comment(
    *,
    file_path: str,
    line: int,
    comment_text: str,
) -> tuple[SuppressionComment | None, list[Diagnostic]]:
    raw = comment_text.strip()
    if _KONSISTENT_PREFIX_RE.match(raw) is None:
        return None, []

    match = _SUPPRESSION_RE.fullmatch(raw)
    if match is None:
        return None, [
            _hygiene_diagnostic(
                file_path=file_path,
                line=line,
                message="Invalid suppression comment: bracketed rule list is required",
            )
        ]

    rules_raw = match.group("rules")
    rules = tuple(rule.strip() for rule in rules_raw.split(","))
    if not rules or any(rule == "" for rule in rules):
        return None, [
            _hygiene_diagnostic(
                file_path=file_path,
                line=line,
                message="Invalid suppression comment: bracketed rule list is required",
            )
        ]

    invalid_rules = [rule for rule in rules if _RULE_NAME_RE.fullmatch(rule) is None]
    if invalid_rules:
        return None, [
            _hygiene_diagnostic(
                file_path=file_path,
                line=line,
                message=f'Invalid suppression rule name "{rule}"',
            )
            for rule in invalid_rules
        ]

    reason = _parse_reason(match.group("tail"))
    if reason is _InvalidReason:
        return None, [
            _hygiene_diagnostic(
                file_path=file_path,
                line=line,
                message="Invalid suppression comment: bracketed rule list is required",
            )
        ]

    return (
        SuppressionComment(
            file_path=file_path,
            line=line,
            kind=match.group("kind"),  # type: ignore[arg-type]
            rules=rules,
            reason=reason,
            raw=raw,
        ),
        [],
    )


class _InvalidReasonType:
    pass


_InvalidReason = _InvalidReasonType()


def _parse_reason(tail: str) -> str | None | _InvalidReasonType:
    if tail == "" or tail.strip() == "":
        return None
    if not tail.startswith(" -- "):
        return _InvalidReason
    reason = tail[4:].strip()
    return reason or None


def _first_code_line(source: str) -> int | None:
    for index, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        return index
    return None


def _is_after_first_code_line(
    *,
    suppression_line: int,
    first_code_line: int | None,
) -> bool:
    return first_code_line is not None and suppression_line >= first_code_line


def _invalid_file_level_placement_diagnostics(
    *,
    suppression: SuppressionComment,
) -> list[Diagnostic]:
    return [
        _hygiene_diagnostic(
            file_path=suppression.file_path,
            line=suppression.line,
            message=(
                f'File-level suppression for "{rule}" must appear before '
                "the first code line"
            ),
        )
        for rule in suppression.rules
    ]


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


def _hygiene_diagnostic(
    *,
    file_path: str,
    line: int,
    message: str,
) -> Diagnostic:
    return create_diagnostic(
        file_path=file_path,
        predicate_name=HYGIENE_CONVENTION_NAME,
        message=message,
        convention_name=HYGIENE_CONVENTION_NAME,
        line=line,
        severity="warning",
    )


__all__ = [
    "HYGIENE_CONVENTION_NAME",
    "AppliedSuppression",
    "SuppressedDiagnostic",
    "SuppressionComment",
    "SuppressionFilterResult",
    "SuppressionKind",
    "SuppressionParseResult",
    "filter_suppressed_diagnostics",
    "parse_suppressions_for_source",
]
