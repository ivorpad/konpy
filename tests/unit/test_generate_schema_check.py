import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_schema.py"


def _load_generate_schema_module():
    spec = importlib.util.spec_from_file_location("generate_schema_check", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGenerateSchemaCheckSubprocess:
    def test_check_exits_zero_against_fresh_artifact(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


class TestGenerateSchemaCheckMismatch:
    def test_check_fails_and_does_not_write_on_mismatch(self, tmp_path, monkeypatch) -> None:
        module = _load_generate_schema_module()
        stale_path = tmp_path / "konpy.schema.json"
        stale_content = '{"stale": true}\n'
        stale_path.write_text(stale_content, encoding="utf-8")
        monkeypatch.setattr(module, "ARTIFACT_PATH", stale_path)

        exit_code = module.main(["--check"])

        assert exit_code != 0
        assert stale_path.read_text(encoding="utf-8") == stale_content

    def test_check_fails_when_artifact_missing(self, tmp_path, monkeypatch) -> None:
        module = _load_generate_schema_module()
        missing_path = tmp_path / "konpy.schema.json"
        monkeypatch.setattr(module, "ARTIFACT_PATH", missing_path)

        exit_code = module.main(["--check"])

        assert exit_code != 0
        assert not missing_path.exists()
