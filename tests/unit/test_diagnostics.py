from __future__ import annotations

from konsistent.core.diagnostics import Diagnostic, create_diagnostic


class TestCreateDiagnostic:
    def test_defaults_expected_found_fix_hint_to_none(self) -> None:
        diagnostic = create_diagnostic(
            file_path="src/index.py",
            predicate_name="haveType",
            message="Expected a file but found a directory",
        )

        assert diagnostic.description is None
        assert diagnostic.hint is None
        assert diagnostic.expected is None
        assert diagnostic.found is None
        assert diagnostic.fix_hint is None

    def test_passes_through_expected_found_fix_hint_when_provided(self) -> None:
        diagnostic = create_diagnostic(
            file_path="src/index.py",
            predicate_name="havePairedFile",
            message="Missing paired file: tests/test_index.py",
            description="Every module needs a matching test file.",
            hint="Consider generating a stub test module.",
            expected="tests/test_index.py",
            found="none",
            fix_hint='Create the paired file at "tests/test_index.py".',
        )

        assert diagnostic.description == "Every module needs a matching test file."
        assert diagnostic.hint == "Consider generating a stub test module."
        assert diagnostic.expected == "tests/test_index.py"
        assert diagnostic.found == "none"
        assert diagnostic.fix_hint == 'Create the paired file at "tests/test_index.py".'

    def test_direct_diagnostic_construction_defaults_new_fields_to_none(self) -> None:
        diagnostic = Diagnostic(
            file_path="src/index.py",
            predicate_name="haveType",
            message="Expected a file but found a directory",
        )

        assert diagnostic.description is None
        assert diagnostic.hint is None
        assert diagnostic.expected is None
        assert diagnostic.found is None
        assert diagnostic.fix_hint is None
