"""Shared artifact path and write helpers for agentic rule proposals."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from konpy.config.errors import Err, Ok, Result


def derive_rules_output_path(pack_path: str | Path) -> Path:
    """Derive ``<pack-stem>.rules.json`` beside a structural pack."""
    destination = Path(pack_path)
    return destination.with_name(f"{destination.stem}.rules.json")


def validate_artifact_destinations(
    *,
    pack_path: str | Path,
    rules_path: str | Path | None,
    report_path: str | Path | None,
) -> Result[None]:
    """Reject active artifact paths that resolve to the same destination."""
    named_paths: list[tuple[str, Path]] = [
        ("reusable convention pack", Path(pack_path))
    ]
    if rules_path is not None:
        named_paths.append(("semantic rules", Path(rules_path)))
    if report_path is not None:
        named_paths.append(("rule-routing report", Path(report_path)))

    normalized: dict[str, tuple[str, Path]] = {}
    try:
        for label, path in named_paths:
            key = os.path.normcase(str(path.expanduser().resolve(strict=False)))
            previous = normalized.get(key)
            if previous is not None:
                previous_label, previous_path = previous
                return Err(
                    "Artifact destinations must be distinct: "
                    f"{previous_label} ({previous_path}) and {label} ({path})."
                )
            normalized[key] = (label, path)
    except OSError as error:
        return Err(f"Could not resolve artifact destinations. {error}")

    return Ok(None)


def write_model_artifact(
    destination: str | Path,
    model: BaseModel,
    *,
    artifact_label: str,
) -> Result[None]:
    """Serialize and write a Pydantic model as stable JSON."""
    path = Path(destination)
    text = (
        json.dumps(
            model.model_dump(
                by_alias=True,
                exclude_none=True,
                mode="json",
            ),
            indent=2,
        )
        + "\n"
    )
    return write_text_artifact(path, text, artifact_label=artifact_label)


def write_text_artifact(
    destination: str | Path,
    text: str,
    *,
    artifact_label: str,
) -> Result[None]:
    """Write a UTF-8 text artifact, creating its parent directory."""
    path = Path(destination)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as error:
        return Err(f"Could not write {artifact_label}: {path}. {error}")

    return Ok(None)


__all__ = [
    "derive_rules_output_path",
    "validate_artifact_destinations",
    "write_model_artifact",
    "write_text_artifact",
]
