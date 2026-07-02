"""Report rendering for `konsistent infer` (M15 convention mining).

Three renderers over the same `InferReport`: JSON (machine-readable),
text and markdown (human/agent-readable).
"""

from __future__ import annotations

import json

from konsistent.infer.models import InferProposal, InferReport, InferSkipped


def render_report_json(report: InferReport) -> str:
    payload = {
        "filesScanned": report.files_scanned,
        "testFilesExcluded": report.test_files_excluded,
        "filesSkippedUnparsable": report.files_skipped_unparsable,
        "filesSkippedUnreadable": report.files_skipped_unreadable,
        "proposals": [_proposal_json(proposal) for proposal in report.proposals],
        "skipped": [_skipped_json(skipped) for skipped in report.skipped],
    }
    return json.dumps(payload, indent=2) + "\n"


def _proposal_json(proposal: InferProposal) -> dict[str, object]:
    return {
        "heuristic": proposal.heuristic,
        "conventionName": proposal.convention_name,
        "scope": proposal.scope,
        "detail": proposal.detail,
        "support": proposal.support,
        "total": proposal.total,
        "confidence": round(proposal.confidence, 4),
        "violators": proposal.violators,
        "omittedViolators": proposal.omitted_violators,
        "convention": proposal.convention,
    }


def _skipped_json(skipped: InferSkipped) -> dict[str, object]:
    return {
        "heuristic": skipped.heuristic,
        "scope": skipped.scope,
        "detail": skipped.detail,
        "support": skipped.support,
        "total": skipped.total,
        "confidence": round(skipped.confidence, 4),
        "reason": skipped.reason,
    }


def _percent(value: float) -> str:
    return f"{value:.0%}"


def render_report_text(report: InferReport) -> str:
    lines: list[str] = [
        f"Scanned {report.files_scanned} files "
        f"({report.test_files_excluded} test files excluded)."
    ]
    if report.files_skipped_unparsable:
        lines.append(f"Skipped {report.files_skipped_unparsable} unparsable file(s).")
    if report.files_skipped_unreadable:
        lines.append(f"Skipped {report.files_skipped_unreadable} unreadable file(s).")

    lines.append("")
    if not report.proposals:
        lines.append("No conventions proposed.")
    else:
        lines.append(f"Proposals ({len(report.proposals)}):")
        for proposal in report.proposals:
            header = (
                f"[{proposal.heuristic}] {proposal.scope} "
                f"({proposal.support}/{proposal.total}, "
                f"{_percent(proposal.confidence)} confidence)"
            )
            lines.append(header)
            lines.append(f"  convention: {proposal.convention_name}")
            if not proposal.violators:
                lines.append("  violators: none")
            else:
                lines.append("  violators:")
                lines.extend(f"    - {violator}" for violator in proposal.violators)
                if proposal.omitted_violators > 0:
                    lines.append(f"    ...and {proposal.omitted_violators} more")

    lines.append("")
    if report.skipped:
        lines.append(f"Skipped signals ({len(report.skipped)}):")
        for skipped in report.skipped:
            detail_suffix = f" ({skipped.detail})" if skipped.detail else ""
            lines.append(
                f"[{skipped.heuristic}] {skipped.scope}{detail_suffix}: "
                f"{skipped.support}/{skipped.total} "
                f"({_percent(skipped.confidence)} confidence) — {skipped.reason}"
            )

    return "\n".join(lines) + "\n"


def render_report_markdown(report: InferReport) -> str:
    lines: list[str] = ["## Infer report", ""]
    lines.append(
        f"Scanned {report.files_scanned} files "
        f"({report.test_files_excluded} test files excluded, "
        f"{report.files_skipped_unparsable} unparsable, "
        f"{report.files_skipped_unreadable} unreadable)."
    )
    lines.append("")

    lines.append("### Proposals")
    lines.append("")
    if not report.proposals:
        lines.append("No conventions proposed.")
    else:
        lines.append("| Heuristic | Scope | Detail | Support/Total | Confidence | Convention |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for proposal in report.proposals:
            lines.append(
                f"| {proposal.heuristic} | {proposal.scope} | {proposal.detail or ''} | "
                f"{proposal.support}/{proposal.total} | {_percent(proposal.confidence)} | "
                f"{proposal.convention_name} |"
            )
            if proposal.violators:
                for violator in proposal.violators:
                    lines.append(f"    - {violator}")
                if proposal.omitted_violators > 0:
                    lines.append(f"    - ...and {proposal.omitted_violators} more")
    lines.append("")

    lines.append("### Skipped signals")
    lines.append("")
    if not report.skipped:
        lines.append("None.")
    else:
        lines.append("| Heuristic | Scope | Detail | Support/Total | Confidence | Reason |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for skipped in report.skipped:
            lines.append(
                f"| {skipped.heuristic} | {skipped.scope} | {skipped.detail or ''} | "
                f"{skipped.support}/{skipped.total} | {_percent(skipped.confidence)} | "
                f"{skipped.reason} |"
            )

    return "\n".join(lines) + "\n"


__all__ = ["render_report_json", "render_report_markdown", "render_report_text"]
