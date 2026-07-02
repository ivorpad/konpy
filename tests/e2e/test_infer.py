from __future__ import annotations

import json
from pathlib import Path


def _fixture(fixtures_dir: Path, name: str) -> Path:
    return fixtures_dir / name


class TestInferBasic:
    def test_clean_fixture_proposes_three_conventions(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "infer-basic"),
            "infer",
            "--heuristic",
            "export-suffix",
            "--heuristic",
            "paired-test-file",
            "--heuristic",
            "barrel-usage",
        )

        assert exit_code == 0

        config = json.loads(stdout)
        names = {convention["name"] for convention in config["conventions"]}
        assert names == {
            "infer-export-suffix-src-services-service",
            "infer-paired-test-file-src-services",
            "infer-barrel-usage-src",
        }

        assert stderr.count("3/3") == 3
        assert stderr.count("100%") == 3


class TestInferBroken:
    def test_broken_fixture_reports_legacy_violator(self, fixtures_dir: Path, run_cli) -> None:
        exit_code, stdout, stderr = run_cli(
            _fixture(fixtures_dir, "infer-broken"),
            "infer",
            "--heuristic",
            "export-suffix",
            "--heuristic",
            "paired-test-file",
            "--min-confidence",
            "0.7",
            "--min-support",
            "3",
        )

        assert exit_code == 0

        config = json.loads(stdout)
        names = {convention["name"] for convention in config["conventions"]}
        assert names == {
            "infer-export-suffix-src-services-service",
            "infer-paired-test-file-src-services",
        }

        assert stderr.count("src/services/legacy_service.py") == 2
        assert "75%" in stderr
