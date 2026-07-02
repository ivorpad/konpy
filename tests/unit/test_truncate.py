from konsistent.core.diagnostics import Diagnostic
from konsistent.core.truncate import format_truncation_message, truncate_diagnostics


def make_diag(msg: str) -> Diagnostic:
    return Diagnostic(file_path="src/foo.py", predicate_name="haveType", message=msg)


class TestTruncateDiagnostics:
    def test_returns_all_diagnostics_when_count_is_within_max(self) -> None:
        diagnostics = [make_diag("a"), make_diag("b")]
        result = truncate_diagnostics(diagnostics=diagnostics, max=5)

        assert len(result.diagnostics) == 2
        assert result.omitted == 0

    def test_returns_all_diagnostics_when_count_equals_max(self) -> None:
        diagnostics = [make_diag("a"), make_diag("b")]
        result = truncate_diagnostics(diagnostics=diagnostics, max=2)

        assert len(result.diagnostics) == 2
        assert result.omitted == 0

    def test_truncates_when_count_exceeds_max(self) -> None:
        diagnostics = [make_diag("a"), make_diag("b"), make_diag("c")]
        result = truncate_diagnostics(diagnostics=diagnostics, max=1)

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].message == "a"
        assert result.omitted == 2

    def test_truncates_to_zero_when_max_is_zero(self) -> None:
        diagnostics = [make_diag("a")]
        result = truncate_diagnostics(diagnostics=diagnostics, max=0)

        assert len(result.diagnostics) == 0
        assert result.omitted == 1


class TestFormatTruncationMessage:
    def test_includes_the_omitted_count(self) -> None:
        assert (
            format_truncation_message(5)
            == "... and 5 more diagnostics (use --max-diagnostics to see more)"
        )

    def test_works_with_one_omitted(self) -> None:
        assert (
            format_truncation_message(1)
            == "... and 1 more diagnostics (use --max-diagnostics to see more)"
        )
