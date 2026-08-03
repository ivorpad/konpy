from __future__ import annotations

from pathlib import Path

from konpy.config.errors import Ok
from konpy.config.loader import load_config_runtime

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestStrictConfigExtendsBaseline:
    """konpy.strict.json must extend konpy.json so the strict dogfood never drops a
    baseline rule by drifting into a parallel policy."""

    def test_strict_runtime_config_includes_baseline_and_strict_conventions(self) -> None:
        result = load_config_runtime(config_path=REPO_ROOT / "konpy.strict.json")

        assert isinstance(result, Ok)
        names = {convention.name for convention in result.value.config.conventions}

        # baseline-only rule (konpy.json)
        assert "packages-have-init" in names
        # strict-only rule (konpy.strict.json)
        assert "max-module-length" in names
