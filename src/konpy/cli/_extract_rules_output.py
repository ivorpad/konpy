"""Artifact writing for `konpy extract-rules`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from konpy.cli._extract_rules_contract import CoveredElsewhereEntry, UnmappedEntry
from konpy.cli._extract_rules_report import format_unmapped_report
from konpy.cli._rule_artifacts import (
    derive_rules_output_path,
    validate_artifact_destinations,
    write_model_artifact,
    write_text_artifact,
)
from konpy.cli._semantic_rules import SemanticRulesPackageV1
from konpy.config.errors import Err, Ok, Result
from konpy.config.schema import ReusableConventionsPackageV1

type WrittenExtractionArtifacts = tuple[Path, Path | None, Path | None]


def write_extraction_artifacts(
    *,
    pack: ReusableConventionsPackageV1,
    semantic_package: SemanticRulesPackageV1,
    destination: Path,
    rules_output_path: str | None,
    report_path: str | None,
    covered_elsewhere: Sequence[CoveredElsewhereEntry],
    unmapped: Sequence[UnmappedEntry],
) -> Result[WrittenExtractionArtifacts]:
    """Write the pack, optional rules package, and optional routing report."""
    rules_destination = _rules_destination(
        destination=destination,
        rules_output_path=rules_output_path,
        has_rules=bool(semantic_package.rules),
    )
    report_destination = Path(report_path) if report_path is not None else None

    collision_result = validate_artifact_destinations(
        pack_path=destination,
        rules_path=rules_destination,
        report_path=report_destination,
    )
    if isinstance(collision_result, Err):
        return collision_result

    write_result = write_model_artifact(
        destination,
        pack,
        artifact_label="extracted reusable convention pack",
    )
    if isinstance(write_result, Err):
        return write_result

    if rules_destination is not None:
        write_result = write_model_artifact(
            rules_destination,
            semantic_package,
            artifact_label="semantic rules",
        )
        if isinstance(write_result, Err):
            return write_result

    if report_destination is not None:
        write_result = write_text_artifact(
            report_destination,
            format_unmapped_report(
                unmapped,
                covered_elsewhere=covered_elsewhere,
                rules_path=rules_destination,
            ),
            artifact_label="rule-routing report",
        )
        if isinstance(write_result, Err):
            return write_result

    return Ok((destination, rules_destination, report_destination))


def _rules_destination(
    *,
    destination: Path,
    rules_output_path: str | None,
    has_rules: bool,
) -> Path | None:
    if not has_rules:
        return None
    if rules_output_path is not None:
        return Path(rules_output_path)
    return derive_rules_output_path(destination)


__all__ = [
    "WrittenExtractionArtifacts",
    "write_extraction_artifacts",
]
