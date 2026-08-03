"""Focused tests for `scripts/eval_unused`'s konpy-vs-vulture overlap matcher.

konpy reports repo-relative paths; vulture reports paths relative to its own
cwd when that cwd happens to sit under the scan target, but falls back to a
fully absolute path when the target is passed as an absolute path from
outside its own tree (see `vulture.utils.format_path`). The matcher must
normalize both representations to the same repo-relative key before
comparing, or an absolute-target run silently reports zero overlap even when
both tools found the same symbol.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

from konpy.core.diagnostics import Diagnostic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_UNUSED_PATH = REPO_ROOT / "scripts" / "eval_unused"


def _load_eval_unused_module() -> ModuleType:
    """Load the extensionless `scripts/eval_unused` script as an importable module."""
    loader = SourceFileLoader("konpy_scripts_eval_unused_matcher", str(EVAL_UNUSED_PATH))
    spec = importlib.util.spec_from_file_location(
        "konpy_scripts_eval_unused_matcher", EVAL_UNUSED_PATH, loader=loader
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestOverlapMatcherAbsoluteTarget:
    def test_absolute_vulture_path_matches_relative_konpy_path(self, tmp_path: Path) -> None:
        """A synthetic shared finding overlaps even when vulture's raw path is
        absolute (as it is when the target itself is passed as an absolute
        path from a cwd outside it) while konpy's is repo-relative."""
        module = _load_eval_unused_module()
        target = tmp_path.resolve()

        diagnostic = Diagnostic(
            file_path="pkg/mod.py",
            predicate_name="unused-code.dead",
            message='"shared_name" is unused',
            line=5,
        )
        vulture_finding = (str(target / "pkg" / "mod.py"), 5, "shared_name")

        konpy_keys = {module._konpy_key(target, diagnostic)}
        vulture_keys = {module._vulture_key(target, vulture_finding)}

        assert konpy_keys & vulture_keys

    def test_relative_vulture_path_still_matches(self, tmp_path: Path) -> None:
        """The pre-existing relative-path case (vulture invoked from a cwd
        under the target) must keep matching after the normalization change."""
        module = _load_eval_unused_module()
        target = tmp_path.resolve()

        diagnostic = Diagnostic(
            file_path="pkg/mod.py",
            predicate_name="unused-code.dead",
            message='"shared_name" is unused',
            line=5,
        )
        vulture_finding = ("pkg/mod.py", 5, "shared_name")

        konpy_keys = {module._konpy_key(target, diagnostic)}
        vulture_keys = {module._vulture_key(target, vulture_finding)}

        assert konpy_keys & vulture_keys

    def test_no_overlap_for_distinct_symbols(self, tmp_path: Path) -> None:
        """Distinct symbols in the same file must not spuriously match."""
        module = _load_eval_unused_module()
        target = tmp_path.resolve()

        diagnostic = Diagnostic(
            file_path="pkg/mod.py",
            predicate_name="unused-code.dead",
            message='"only_konpy_finds_this" is unused',
            line=5,
        )
        vulture_finding = (str(target / "pkg" / "mod.py"), 9, "only_vulture_finds_this")

        konpy_keys = {module._konpy_key(target, diagnostic)}
        vulture_keys = {module._vulture_key(target, vulture_finding)}

        assert not (konpy_keys & vulture_keys)
