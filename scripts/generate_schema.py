"""Generate konpy.schema.json from the pydantic config models.

Run from the repo root: uv run python scripts/generate_schema.py
The artifact is checked in; tests/unit/test_schema_artifact.py asserts freshness.

Use --check to verify the artifact is current without writing it (e.g. in CI).
"""

import argparse
import json
import sys
from pathlib import Path

from konpy.config.schema import RawConfigV1

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = REPO_ROOT / "konpy.schema.json"

STALE_MESSAGE = "konpy.schema.json is stale; run: uv run python scripts/generate_schema.py"


def generate_schema_text() -> str:
    schema = RawConfigV1.model_json_schema(by_alias=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "konpy configuration",
        "description": (
            "Configuration file for konpy, a CLI linter that enforces "
            "structural conventions in Python codebases."
        ),
        **schema,
    }
    return json.dumps(schema, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the artifact is current without writing it",
    )
    args = parser.parse_args(argv)

    if args.check:
        current = ARTIFACT_PATH.is_file() and ARTIFACT_PATH.read_text(
            encoding="utf-8"
        ) == generate_schema_text()
        if current:
            return 0
        print(STALE_MESSAGE, file=sys.stderr)
        return 1

    ARTIFACT_PATH.write_text(generate_schema_text(), encoding="utf-8")
    print(f"wrote {ARTIFACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
