import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_schema import ARTIFACT_PATH, generate_schema_text  # noqa: E402


class TestSchemaArtifact:
    def test_artifact_exists(self) -> None:
        assert ARTIFACT_PATH.is_file()

    def test_artifact_is_fresh(self) -> None:
        checked_in = ARTIFACT_PATH.read_text(encoding="utf-8")
        regenerated = generate_schema_text()
        assert checked_in == regenerated, (
            "konpy.schema.json is stale — run: uv run python scripts/generate_schema.py"
        )

    def test_artifact_declares_v1(self) -> None:
        import json

        schema = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        assert schema["properties"]["version"]["const"] == "v1"
        assert "conventions" in schema["properties"]
