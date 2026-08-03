"""Lane-aware report formatting for rule extraction and promotion."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from konpy.cli._extract_rules_contract import CoveredElsewhereEntry, UnmappedEntry


def format_unmapped_stdout(
    unmapped: Sequence[UnmappedEntry],
    *,
    covered_elsewhere: Sequence[CoveredElsewhereEntry] = (),
    rules_path: str | Path | None = None,
) -> str:
    """Format rule-routing results for stdout."""
    sections = [
        _format_covered_stdout(covered_elsewhere),
        _format_unmapped_stdout_section(unmapped),
    ]
    if rules_path is not None:
        sections.append(_wiring_hint(rules_path))
    return "\n\n".join(sections) + "\n"


def format_unmapped_report(
    unmapped: Sequence[UnmappedEntry],
    *,
    covered_elsewhere: Sequence[CoveredElsewhereEntry] = (),
    rules_path: str | Path | None = None,
) -> str:
    """Format rule-routing results as Markdown."""
    lines = [
        "# Rule routing report",
        "",
        "## Covered by existing linters",
        "",
    ]

    if covered_elsewhere:
        lines.extend(_covered_markdown_lines(covered_elsewhere))
    else:
        lines.append("None.")

    lines.extend(["", "## Unmapped rules", ""])
    if unmapped:
        lines.extend(
            f"- **{item['rule']}**: {item['reason']}" for item in unmapped
        )
    else:
        lines.append("None.")

    if rules_path is not None:
        lines.extend(
            [
                "",
                "## Semantic hook wiring",
                "",
                _wiring_hint(rules_path),
            ]
        )

    return "\n".join(lines) + "\n"


def _format_covered_stdout(
    covered_elsewhere: Sequence[CoveredElsewhereEntry],
) -> str:
    if not covered_elsewhere:
        return "Covered by existing linters: none"

    lines = ["Covered by existing linters:"]
    lines.extend(_covered_plain_lines(covered_elsewhere))
    return "\n".join(lines)


def _format_unmapped_stdout_section(
    unmapped: Sequence[UnmappedEntry],
) -> str:
    if not unmapped:
        return "Unmapped rules: none"

    lines = ["Unmapped rules:"]
    lines.extend(f"- {item['rule']}: {item['reason']}" for item in unmapped)
    return "\n".join(lines)


def _covered_plain_lines(
    covered_elsewhere: Sequence[CoveredElsewhereEntry],
) -> list[str]:
    lines: list[str] = []
    for item in covered_elsewhere:
        line = f"- {item['rule']}: {item['tool']}"
        note = item.get("note")
        if note:
            line += f" — {note}"
        lines.append(line)
    return lines


def _covered_markdown_lines(
    covered_elsewhere: Sequence[CoveredElsewhereEntry],
) -> list[str]:
    lines: list[str] = []
    for item in covered_elsewhere:
        line = f"- **{item['rule']}**: {item['tool']}"
        note = item.get("note")
        if note:
            line += f" — {note}"
        lines.append(line)
    return lines


def _wiring_hint(rules_path: str | Path) -> str:
    return (
        "Add a PostToolUse hook: konpy hook --match '**/*.py' "
        f"--rules {rules_path} --agent claude"
    )


__all__ = [
    "format_unmapped_report",
    "format_unmapped_stdout",
]
