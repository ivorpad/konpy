"""Guards keeping `scripts/eval_unused` a non-authoritative side tool.

It must never be wired into `scripts/verify` -- it is a comparison harness
for eyeballing agreement with `vulture`, not a verification step.
"""

from __future__ import annotations

import importlib.util
import stat
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_PATH = REPO_ROOT / "scripts" / "verify"
EVAL_UNUSED_PATH = REPO_ROOT / "scripts" / "eval_unused"


def _load_eval_unused_module() -> ModuleType:
    """Load the extensionless `scripts/eval_unused` script as an importable module.

    `exec_module` runs top-level code but never calls `main()` -- the script
    guards its entry point behind `if __name__ == "__main__":`, so loading it
    for inspection has no side effects.
    """
    loader = SourceFileLoader("konpy_scripts_eval_unused", str(EVAL_UNUSED_PATH))
    spec = importlib.util.spec_from_file_location(
        "konpy_scripts_eval_unused", EVAL_UNUSED_PATH, loader=loader
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestNeverReferencedByVerify:
    def test_verify_source_never_mentions_eval_unused(self) -> None:
        source = VERIFY_PATH.read_text(encoding="utf-8")
        assert "eval_unused" not in source


class TestModuleLoadsWithoutRunningMain:
    def test_is_executable(self) -> None:
        mode = EVAL_UNUSED_PATH.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_shebang(self) -> None:
        first_line = EVAL_UNUSED_PATH.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/usr/bin/env python3"

    def test_module_loads_and_exposes_main(self) -> None:
        module = _load_eval_unused_module()
        assert callable(module.main)
