from __future__ import annotations

import json

from konpy.infer.models import InferProposal, InferReport, InferSkipped
from konpy.infer.report import render_report_json, render_report_markdown, render_report_text


def sample_report(*, with_proposals: bool = True, with_skipped: bool = True) -> InferReport:
    proposals = (
        [
            InferProposal(
                heuristic="export-suffix",
                convention_name="infer-export-suffix-src-services-service",
                scope="src/services",
                detail=None,
                support=47,
                total=50,
                confidence=0.94,
                violators=["src/services/legacy_thing.py"],
                omitted_violators=0,
                convention={"name": "infer-export-suffix-src-services-service"},
            )
        ]
        if with_proposals
        else []
    )
    skipped = (
        [
            InferSkipped(
                heuristic="import-dominance",
                scope="scripts",
                detail=None,
                support=1,
                total=2,
                confidence=0.5,
                reason="below-min-confidence",
            )
        ]
        if with_skipped
        else []
    )
    return InferReport(
        files_scanned=128,
        test_files_excluded=34,
        files_skipped_unparsable=0,
        files_skipped_unreadable=0,
        proposals=proposals,
        skipped=skipped,
    )


class TestRenderers:
    def test_json_shape(self) -> None:
        payload = json.loads(render_report_json(sample_report()))

        assert set(payload.keys()) == {
            "filesScanned",
            "testFilesExcluded",
            "filesSkippedUnparsable",
            "filesSkippedUnreadable",
            "proposals",
            "skipped",
        }
        proposal = payload["proposals"][0]
        assert proposal["conventionName"] == "infer-export-suffix-src-services-service"
        assert proposal["omittedViolators"] == 0
        assert proposal["confidence"] == 0.94

        skipped = payload["skipped"][0]
        assert isinstance(skipped["reason"], str)

    def test_text_renderer_includes_key_facts(self) -> None:
        text = render_report_text(sample_report())

        assert "export-suffix" in text
        assert "src/services" in text
        assert "47/50" in text
        assert "94%" in text
        assert "src/services/legacy_thing.py" in text
        assert "below-min-confidence" in text

    def test_text_renderer_notes_no_proposals(self) -> None:
        text = render_report_text(sample_report(with_proposals=False, with_skipped=False))

        assert "No conventions proposed" in text

    def test_markdown_renderer_includes_key_facts(self) -> None:
        markdown = render_report_markdown(sample_report())

        assert "## Infer report" in markdown
        assert "export-suffix" in markdown
        assert "src/services" in markdown
        assert "47/50" in markdown
        assert "94%" in markdown
        assert "src/services/legacy_thing.py" in markdown
        assert "below-min-confidence" in markdown
