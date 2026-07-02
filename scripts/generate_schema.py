"""Generate konsistent.schema.json from the pydantic config models.

Run from the repo root: uv run python scripts/generate_schema.py
The artifact is checked in; tests/unit/test_schema_artifact.py asserts freshness.
"""

import json
from pathlib import Path

from konsistent.config.schema import RawConfigV1

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = REPO_ROOT / "konsistent.schema.json"


def generate_schema_text() -> str:
    schema = RawConfigV1.model_json_schema(by_alias=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "konsistent configuration",
        "description": (
            "Configuration file for konsistent, a CLI linter that enforces "
            "structural conventions in Python codebases."
        ),
        **schema,
    }
    return json.dumps(schema, indent=2, sort_keys=False) + "\n"


def main() -> None:
    ARTIFACT_PATH.write_text(generate_schema_text(), encoding="utf-8")
    print(f"wrote {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
