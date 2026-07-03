from __future__ import annotations

import json
from pathlib import Path

import pytest

from konpy.config.schema import ReusableConventionsPackageV1
from konpy.predicates.registry import builtin_predicate_registry

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKS_DIR = REPO_ROOT / "packs"

PACK_FILENAMES = [
    "python-best-practices.json",
    "hexagonal-architecture.json",
    "src-layout.json",
]


def _load(filename: str) -> dict:
    return json.loads((PACKS_DIR / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename", PACK_FILENAMES)
class TestPackSchemaValidation:
    def test_pack_validates_against_reusable_convention_schema(self, filename: str) -> None:
        data = _load(filename)
        registry = builtin_predicate_registry()

        package = ReusableConventionsPackageV1.model_validate(
            data, context=registry.validation_context()
        )

        assert package.conventionSpecVersion == "v1"
        assert len(package.conventions) > 0

    def test_pack_convention_names_are_unique(self, filename: str) -> None:
        data = _load(filename)
        names = [convention["name"] for convention in data["conventions"]]
        assert len(names) == len(set(names))

    def test_pack_conventions_have_name_and_description(self, filename: str) -> None:
        data = _load(filename)
        for convention in data["conventions"]:
            assert convention.get("name")
            assert convention.get("description")

    def test_pack_conventions_have_hint(self, filename: str) -> None:
        data = _load(filename)
        for convention in data["conventions"]:
            assert convention.get("hint"), (
                f"convention {convention.get('name')!r} in {filename} is missing a "
                "non-empty 'hint' giving intent-first fix guidance"
            )
