from __future__ import annotations

import textwrap
from collections.abc import Mapping
from itertools import groupby

from pydantic import ValidationError

from konpy.config.schema import ReusableConventionsPackageV1
from konpy.core.filesystem import FakeFileSystem
from konpy.infer.engine import HEURISTIC_NAMES, build_pack, run_infer


def fs(contents: Mapping[str, str]) -> FakeFileSystem:
    return FakeFileSystem(
        contents={path: textwrap.dedent(body).lstrip("\n") for path, body in contents.items()}
    )


def service_module(class_name: str) -> str:
    return f"""
        \"\"\"{class_name} module.\"\"\"

        import os


        class {class_name}:
            \"\"\"Handles {class_name}.\"\"\"

            def get(self, item_id: int) -> str:
                \"\"\"Get item.\"\"\"
                return os.fspath(str(item_id))
        """


def full_fixture() -> FakeFileSystem:
    return fs(
        {
            "src/services/user_service.py": service_module("UserService"),
            "src/services/order_service.py": service_module("OrderService"),
            "src/services/billing_service.py": service_module("BillingService"),
            "src/services/__init__.py": '"""Services package."""\n',
            "src/other/__init__.py": '"""Other package."""\n',
            "src/__init__.py": '"""Src package."""\n',
            "tests/test_user_service.py": '"""Tests."""\n',
            "tests/test_order_service.py": '"""Tests."""\n',
            "tests/test_billing_service.py": '"""Tests."""\n',
        }
    )


class TestRunInfer:
    def test_proposals_ordered_by_heuristic_then_scope(self) -> None:
        report = run_infer(file_system=full_fixture())

        indices = [HEURISTIC_NAMES.index(p.heuristic) for p in report.proposals]
        assert indices == sorted(indices)

        for _, group in groupby(report.proposals, key=lambda p: p.heuristic):
            scopes = [p.scope for p in group]
            assert scopes == sorted(scopes)

        heuristics_present = {p.heuristic for p in report.proposals}
        assert {"export-suffix", "paired-test-file", "barrel-usage"} <= heuristics_present

    def test_directory_slug_collision_gets_deterministic_suffix(self) -> None:
        file_system = fs(
            {
                "src/a-b/foo_service.py": "class FooService:\n    pass\n",
                "src/a-b/bar_service.py": "class BarService:\n    pass\n",
                "src/a-b/baz_service.py": "class BazService:\n    pass\n",
                "src/a_b/foo_service.py": "class FooService:\n    pass\n",
                "src/a_b/bar_service.py": "class BarService:\n    pass\n",
                "src/a_b/baz_service.py": "class BazService:\n    pass\n",
            }
        )

        report = run_infer(
            file_system=file_system,
            heuristics=["export-suffix"],
            min_confidence=0.9,
            min_support=3,
        )

        names = [p.convention_name for p in report.proposals]
        assert names == [
            "infer-export-suffix-src-a-b-service",
            "infer-export-suffix-src-a-b-service-2",
        ]

    def test_heuristic_filter_suppresses_other_heuristics(self) -> None:
        report = run_infer(
            file_system=full_fixture(),
            heuristics=["export-suffix"],
        )

        assert report.proposals
        assert all(p.heuristic == "export-suffix" for p in report.proposals)
        assert all(s.heuristic == "export-suffix" for s in report.skipped)

    def test_thresholds_and_max_violators_are_threaded_through(self) -> None:
        contents = {
            f"src/f{i}_service.py": f"class F{i}Service:\n    pass\n" for i in range(3)
        }
        contents.update(
            {f"src/g{i}_service.py": f"class Wrong{i}:\n    pass\n" for i in range(12)}
        )
        file_system = fs(contents)

        report = run_infer(
            file_system=file_system,
            heuristics=["export-suffix"],
            min_confidence=0.0,
            min_support=1,
            max_violators=5,
        )

        assert len(report.proposals) == 1
        proposal = report.proposals[0]
        assert proposal.support == 3
        assert proposal.total == 15
        assert len(proposal.violators) == 5
        assert proposal.omitted_violators == 7

    def test_build_pack_validates_against_reusable_pack_schema(self) -> None:
        report = run_infer(file_system=full_fixture())

        heuristics_present = {p.heuristic for p in report.proposals}
        assert heuristics_present == set(HEURISTIC_NAMES)

        raw = build_pack(report)
        assert raw["conventionSpecVersion"] == "v1"
        try:
            ReusableConventionsPackageV1.model_validate(raw)
        except ValidationError as error:  # pragma: no cover - failure path
            raise AssertionError(str(error)) from error

    def test_file_counts_are_correct_end_to_end(self) -> None:
        file_system = FakeFileSystem(
            files=["src/unreadable.py"],
            contents={
                "src/a.py": "x = 1\n",
                "src/broken.py": "def (:\n",
                "tests/test_a.py": '"""Tests."""\n',
            },
        )

        report = run_infer(file_system=file_system)

        assert report.files_scanned == 2
        assert report.test_files_excluded == 1
        assert report.files_skipped_unparsable == 1
        assert report.files_skipped_unreadable == 1
