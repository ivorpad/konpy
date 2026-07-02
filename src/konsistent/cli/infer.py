from __future__ import annotations

import json
import sys
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from konsistent.config.errors import format_validation_error
from konsistent.config.schema import ReusableConventionsPackageV1
from konsistent.core.filesystem import FileSystem, RealFileSystem
from konsistent.infer.engine import (
    DEFAULT_INFER_INCLUDE,
    DEFAULT_INFER_TEST_GLOBS,
    HEURISTIC_NAMES,
    build_pack,
    run_infer,
)
from konsistent.infer.models import InferReport
from konsistent.infer.report import render_report_json, render_report_markdown, render_report_text


class InferReportFormat(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"


_RENDERERS: dict[str, Callable[[InferReport], str]] = {
    "text": render_report_text,
    "markdown": render_report_markdown,
    "json": render_report_json,
}


def run_infer_command(
    *,
    include: list[str] | None,
    exclude: list[str] | None,
    test_glob: list[str] | None,
    min_confidence: float,
    min_support: int,
    max_violators: int,
    heuristic: list[str] | None,
    format: InferReportFormat | str = InferReportFormat.TEXT,
    output_path: str | None,
    report_path: str | None,
    file_system: FileSystem | None = None,
) -> int:
    if not (0.0 <= min_confidence <= 1.0):
        _write_error("--min-confidence must be between 0.0 and 1.0 inclusive.")
        return 1

    if min_support < 1:
        _write_error("--min-support must be at least 1.")
        return 1

    if max_violators < 0:
        _write_error("--max-violators must be zero or greater.")
        return 1

    if heuristic:
        unknown = [name for name in heuristic if name not in HEURISTIC_NAMES]
        if unknown:
            _write_error(
                f"Unknown --heuristic value(s): {', '.join(unknown)}. "
                f"Expected one of: {', '.join(HEURISTIC_NAMES)}."
            )
            return 1

    fs = file_system or RealFileSystem(cwd=Path.cwd())

    report = run_infer(
        file_system=fs,
        include=tuple(include) if include else DEFAULT_INFER_INCLUDE,
        exclude=tuple(exclude) if exclude else (),
        test_globs=tuple(test_glob) if test_glob else DEFAULT_INFER_TEST_GLOBS,
        min_confidence=min_confidence,
        min_support=min_support,
        max_violators=max_violators,
        heuristics=heuristic,
    )

    raw_pack = build_pack(report)
    try:
        validated = ReusableConventionsPackageV1.model_validate(raw_pack)
    except ValidationError as error:
        _write_error(
            "Internal error: generated pack failed schema validation:\n"
            f"{format_validation_error(error)}"
        )
        return 1

    pack_json = (
        json.dumps(validated.model_dump(by_alias=True, exclude_none=True, mode="json"), indent=2)
        + "\n"
    )

    if output_path is None:
        sys.stdout.write(pack_json)
    else:
        destination = Path(output_path)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(pack_json, encoding="utf-8")
        except OSError as error:
            _write_error(f"Could not write proposed pack: {destination}. {error}")
            return 1
        sys.stdout.write(f"Wrote proposed pack to {destination}\n")

    resolved_format = format.value if isinstance(format, InferReportFormat) else str(format)
    report_text = _RENDERERS[resolved_format](report)

    if report_path is None:
        sys.stderr.write(report_text)
    else:
        report_destination = Path(report_path)
        try:
            report_destination.parent.mkdir(parents=True, exist_ok=True)
            report_destination.write_text(report_text, encoding="utf-8")
        except OSError as error:
            _write_error(f"Could not write infer report: {report_destination}. {error}")
            return 1
        sys.stderr.write(f"Wrote infer report to {report_destination}\n")

    return 0


def _write_error(message: str) -> None:
    sys.stderr.write(f"{message}\n")


__all__ = ["InferReportFormat", "run_infer_command"]
