from __future__ import annotations

from konpy.core.context import PredicateContext
from konpy.core.filesystem import FakeFileSystem
from konpy.predicates.match_content import check_match_content


def context(*, path: str = "src/service.py") -> PredicateContext:
    return PredicateContext(
        path=path,
        placeholders={},
        file_system=FakeFileSystem(),
        base_path="src",
    )


class TestCheckMatchContent:
    def test_returns_no_diagnostics_when_all_regexes_match(self) -> None:
        file_system = FakeFileSystem(
            contents={
                "src/service.py": (
                    "# SPDX-License-Identifier: Apache-2.0\n"
                    "class Service:\n"
                    "    pass\n"
                )
            }
        )

        result = check_match_content(
            expected=["SPDX-License-Identifier", r"class\s+Service"],
            context=context(),
            file_system=file_system,
        )

        assert result == []

    def test_returns_diagnostic_for_each_missing_regex(self) -> None:
        file_system = FakeFileSystem(
            contents={"src/service.py": "class Service:\n    pass\n"}
        )

        result = check_match_content(
            expected=["SPDX-License-Identifier", r"def\s+create_service"],
            context=context(),
            file_system=file_system,
        )

        assert len(result) == 2
        assert result[0].predicate_name == "matchContent"
        assert (
            result[0].message
            == 'File content must match regex "SPDX-License-Identifier"'
        )
        assert result[1].message == 'File content must match regex "def\\s+create_service"'

    def test_uses_python_re_multiline_matching(self) -> None:
        file_system = FakeFileSystem(
            contents={"src/service.py": "class Service:\n    pass\n"}
        )

        result = check_match_content(
            expected=[r"^    pass$"],
            context=context(),
            file_system=file_system,
        )

        assert result == []

    def test_defensively_reports_invalid_regex(self) -> None:
        file_system = FakeFileSystem(contents={"src/service.py": "content\n"})

        result = check_match_content(
            expected=["["],
            context=context(),
            file_system=file_system,
        )

        assert len(result) == 1
        assert result[0].predicate_name == "matchContent"
        assert result[0].message.startswith('Invalid regex "[": ')

    def test_includes_convention_name_and_severity_when_provided(self) -> None:
        file_system = FakeFileSystem(contents={"src/service.py": "content\n"})

        result = check_match_content(
            expected=["SPDX-License-Identifier"],
            context=context(),
            file_system=file_system,
            convention_name="license-header",
            severity="warning",
        )

        assert len(result) == 1
        assert result[0].convention_name == "license-header"
        assert result[0].severity == "warning"
        assert result[0].file_path == "src/service.py"

    def test_missing_match_diagnostic_includes_expected_and_fix_hint(self) -> None:
        file_system = FakeFileSystem(contents={"src/service.py": "content\n"})

        result = check_match_content(
            expected=["SPDX-License-Identifier"],
            context=context(),
            file_system=file_system,
        )

        assert result[0].expected == "SPDX-License-Identifier"
        assert result[0].fix_hint is not None
        assert "SPDX-License-Identifier" in result[0].fix_hint
        assert "src/service.py" in result[0].fix_hint

    def test_invalid_regex_diagnostic_includes_expected_and_found(self) -> None:
        file_system = FakeFileSystem(contents={"src/service.py": "content\n"})

        result = check_match_content(
            expected=["["],
            context=context(),
            file_system=file_system,
        )

        assert result[0].expected == "["
        assert isinstance(result[0].found, str)
        assert result[0].found != ""
