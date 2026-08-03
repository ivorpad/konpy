from __future__ import annotations

import io
import re
import tokenize as py_tokenize
from dataclasses import dataclass
from typing import Literal

from konpy.core.diagnostics import Diagnostic, create_diagnostic

SuppressionKind = Literal["ignore", "ignore-file"]

_RULE_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_KONPY_PREFIX_RE = re.compile(r"^#\s*konpy:")
_SUPPRESSION_RE = re.compile(
    r"^#\s*konpy:\s*"
    r"(?P<kind>ignore|ignore-file)"
    r"\[(?P<rules>[^\]]*)\]"
    r"(?P<tail>.*)$"
)

HYGIENE_CONVENTION_NAME = "suppressions"


@dataclass(frozen=True, kw_only=True)
class SuppressionComment:
    """A single parsed `# konpy: ignore[...]` / `ignore-file[...]` comment."""

    file_path: str
    line: int
    kind: SuppressionKind
    rules: tuple[str, ...]
    reason: str | None
    raw: str


@dataclass(frozen=True, kw_only=True)
class SuppressionParseResult:
    """The suppression comments found in a source file, plus any parse-error diagnostics."""

    suppressions: list[SuppressionComment]
    diagnostics: list[Diagnostic]


def parse_suppressions_for_source(
    *,
    file_path: str,
    source: str,
) -> SuppressionParseResult:
    """Extract `# konpy: ignore[...]`/`ignore-file[...]` comments from source.

    Malformed suppression comments and misplaced `ignore-file` comments are
    reported as hygiene diagnostics rather than raising.
    """
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
    if _KONPY_PREFIX_RE.match(raw) is None:
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
    if isinstance(reason, _InvalidReasonType):
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
    "SuppressionComment",
    "SuppressionKind",
    "SuppressionParseResult",
    "parse_suppressions_for_source",
]
