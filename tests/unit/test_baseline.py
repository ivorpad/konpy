from __future__ import annotations

import pytest

from konpy.core.baseline import (
    BASELINE_VERSION,
    BaselineData,
    BaselineStaleEntry,
    apply_baseline,
    build_baseline,
    load_baseline,
    serialize_baseline,
)
from konpy.core.diagnostics import Diagnostic

CANONICAL_BASELINE = (
    "{\n"
    '  "baselineVersion": "v1",\n'
    '  "entries": {\n'
    '    "src/a.py": {\n'
    '      "conv-name": 2\n'
    "    }\n"
    "  }\n"
    "}\n"
)


def diagnostic(
    *,
    file_path: str = "src/a.py",
    convention_name: str | None = "conv-name",
    predicate_name: str = "predicateName",
    line: int | None = 1,
    column: int | None = 0,
    message: str = "test diagnostic",
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        predicate_name=predicate_name,
        message=message,
        convention_name=convention_name,
        line=line,
        column=column,
    )


class TestLoadBaseline:
    def test_round_trips_a_canonical_document_byte_for_byte(self) -> None:
        assert serialize_baseline(load_baseline(CANONICAL_BASELINE)) == CANONICAL_BASELINE

    def test_loads_empty_entries(self) -> None:
        data = load_baseline('{"baselineVersion": "v1", "entries": {}}')

        assert data == BaselineData(baseline_version="v1", entries={})

    def test_defaults_missing_entries_to_empty(self) -> None:
        data = load_baseline('{"baselineVersion": "v1"}')

        assert data.entries == {}

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            load_baseline("not json")

    def test_rejects_non_object_top_level(self) -> None:
        with pytest.raises(ValueError, match="expected a JSON object"):
            load_baseline("[]")

    def test_rejects_wrong_version(self) -> None:
        with pytest.raises(ValueError, match="baselineVersion"):
            load_baseline('{"baselineVersion": "v2", "entries": {}}')

    def test_rejects_missing_version(self) -> None:
        with pytest.raises(ValueError, match="baselineVersion"):
            load_baseline('{"entries": {}}')

    def test_rejects_unknown_top_level_key(self) -> None:
        with pytest.raises(ValueError, match="unknown top-level key"):
            load_baseline('{"baselineVersion": "v1", "entries": {}, "extra": true}')

    def test_rejects_string_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            load_baseline('{"baselineVersion": "v1", "entries": {"src/a.py": {"rule": "2"}}}')

    def test_rejects_negative_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            load_baseline('{"baselineVersion": "v1", "entries": {"src/a.py": {"rule": -1}}}')

    def test_rejects_boolean_count(self) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            load_baseline('{"baselineVersion": "v1", "entries": {"src/a.py": {"rule": true}}}')

    def test_rejects_non_object_entries(self) -> None:
        with pytest.raises(ValueError, match='"entries" must be an object'):
            load_baseline('{"baselineVersion": "v1", "entries": []}')

    def test_rejects_non_object_file_entry(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            load_baseline('{"baselineVersion": "v1", "entries": {"src/a.py": 2}}')


class TestSerializeBaseline:
    def test_sorts_file_and_convention_keys(self) -> None:
        data = BaselineData(
            baseline_version="v1",
            entries={
                "src/b.py": {"z-rule": 1, "a-rule": 2},
                "src/a.py": {"rule": 1},
            },
        )

        assert serialize_baseline(data) == (
            "{\n"
            '  "baselineVersion": "v1",\n'
            '  "entries": {\n'
            '    "src/a.py": {\n'
            '      "rule": 1\n'
            "    },\n"
            '    "src/b.py": {\n'
            '      "a-rule": 2,\n'
            '      "z-rule": 1\n'
            "    }\n"
            "  }\n"
            "}\n"
        )


class TestBuildBaseline:
    def test_counts_diagnostics_per_file_and_convention(self) -> None:
        data = build_baseline(
            [
                diagnostic(file_path="src/a.py", convention_name="rule-a"),
                diagnostic(file_path="src/a.py", convention_name="rule-a"),
                diagnostic(file_path="src/a.py", convention_name="rule-b"),
                diagnostic(file_path="src/b.py", convention_name="rule-a"),
            ]
        )

        assert data == BaselineData(
            baseline_version=BASELINE_VERSION,
            entries={
                "src/a.py": {"rule-a": 2, "rule-b": 1},
                "src/b.py": {"rule-a": 1},
            },
        )

    def test_falls_back_to_predicate_name_when_convention_name_is_absent(self) -> None:
        data = build_baseline(
            [
                diagnostic(convention_name=None, predicate_name="haveType"),
                diagnostic(convention_name=None, predicate_name="haveType"),
            ]
        )

        assert data.entries == {"src/a.py": {"haveType": 2}}

    def test_empty_diagnostics_produce_empty_entries(self) -> None:
        assert build_baseline([]) == BaselineData(baseline_version=BASELINE_VERSION, entries={})


class TestApplyBaseline:
    def test_demotes_exactly_recorded_count_in_line_column_order(self) -> None:
        diagnostics = [
            diagnostic(line=3, column=0, message="third"),
            diagnostic(line=1, column=0, message="first"),
            diagnostic(line=2, column=0, message="second"),
        ]
        baseline = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv-name": 2}},
        )

        result = apply_baseline(diagnostics=diagnostics, baseline=baseline)

        assert [item.diagnostic.message for item in result.baselined] == ["first", "second"]
        assert [d.message for d in result.remaining] == ["third"]
        assert result.stale_entries == []

    def test_overflow_beyond_recorded_count_stays_in_remaining(self) -> None:
        diagnostics = [
            diagnostic(line=1, message="one"),
            diagnostic(line=2, message="two"),
            diagnostic(line=3, message="three"),
        ]
        baseline = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv-name": 2}},
        )

        result = apply_baseline(diagnostics=diagnostics, baseline=baseline)

        assert len(result.baselined) == 2
        assert len(result.remaining) == 1
        assert result.remaining[0].message == "three"

    def test_stale_entry_when_fewer_diagnostics_found_than_recorded(self) -> None:
        diagnostics = [diagnostic(line=1, message="only-one")]
        baseline = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv-name": 3}},
        )

        result = apply_baseline(diagnostics=diagnostics, baseline=baseline)

        assert len(result.baselined) == 1
        assert result.remaining == []
        assert result.stale_entries == [
            _stale(file_path="src/a.py", convention_name="conv-name", recorded=3, found=1)
        ]

    def test_stale_entry_when_file_absent_from_diagnostics_entirely(self) -> None:
        baseline = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv-name": 2}},
        )

        result = apply_baseline(diagnostics=[], baseline=baseline)

        assert result.baselined == []
        assert result.remaining == []
        assert result.stale_entries == [
            _stale(file_path="src/a.py", convention_name="conv-name", recorded=2, found=0)
        ]

    def test_no_baseline_entry_leaves_all_diagnostics_in_remaining(self) -> None:
        diagnostics = [diagnostic(message="new")]

        result = apply_baseline(
            diagnostics=diagnostics,
            baseline=BaselineData(baseline_version="v1", entries={}),
        )

        assert result.baselined == []
        assert result.remaining == diagnostics
        assert result.stale_entries == []

    def test_preserves_original_diagnostic_order_in_remaining(self) -> None:
        diagnostics = [
            diagnostic(file_path="src/b.py", convention_name="rule-b", line=5, message="b"),
            diagnostic(file_path="src/a.py", convention_name="rule-a", line=1, message="a"),
        ]

        result = apply_baseline(
            diagnostics=diagnostics,
            baseline=BaselineData(baseline_version="v1", entries={}),
        )

        assert [d.message for d in result.remaining] == ["b", "a"]

    def test_deterministic_across_repeated_calls(self) -> None:
        diagnostics = [
            diagnostic(line=3, message="third"),
            diagnostic(line=1, message="first"),
            diagnostic(line=2, message="second"),
        ]
        baseline = BaselineData(
            baseline_version="v1",
            entries={"src/a.py": {"conv-name": 2}},
        )

        first = apply_baseline(diagnostics=diagnostics, baseline=baseline)
        second = apply_baseline(diagnostics=diagnostics, baseline=baseline)

        assert [d.message for d in first.remaining] == [d.message for d in second.remaining]
        assert [b.diagnostic.message for b in first.baselined] == [
            b.diagnostic.message for b in second.baselined
        ]


def _stale(
    *, file_path: str, convention_name: str, recorded: int, found: int
) -> BaselineStaleEntry:
    return BaselineStaleEntry(
        file_path=file_path,
        convention_name=convention_name,
        recorded_count=recorded,
        found_count=found,
    )
