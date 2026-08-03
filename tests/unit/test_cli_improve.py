from __future__ import annotations

from pathlib import Path

import pytest

from konpy.cli._improve_prompt import build_improve_prompt, format_finding_block
from konpy.cli.agent_runner import AgentInvocation, AgentRunResult, ExtractAgent
from konpy.cli.improve import run_improve_command
from konpy.config.errors import Err, Ok
from konpy.core._improve_groups import select_group
from konpy.core._report_model import ReportFunctionGroup
from konpy.predicates.restrict_duplicate_functions import FIX_HINT

_DIFF = (
    "--- a/src/a.py\n"
    "+++ b/src/a.py\n"
    "@@ -1,3 +1,4 @@\n"
    " def calculate_a(value):\n"
    "+    pass\n"
    "\n"
    "Rationale: extracted the shared body into one helper."
)


def cross_component_group(*, name_variants: tuple[str, ...] = ()) -> ReportFunctionGroup:
    return ReportFunctionGroup(
        name="calculate_a",
        statement_count=5,
        members=(("pkg_a/a.py", 3), ("pkg_b/b.py", 7)),
        name_variants=name_variants,
        is_cross_component=True,
    )


def same_component_group(name: str = "helper") -> ReportFunctionGroup:
    return ReportFunctionGroup(
        name=name,
        statement_count=4,
        members=(("pkg/a.py", 1), ("pkg/b.py", 9)),
        is_cross_component=False,
    )


class FakeRunner:
    def __init__(self, response: AgentRunResult | str) -> None:
        self.response = response
        self.calls: list[tuple[AgentInvocation, str]] = []

    def __call__(self, invocation: AgentInvocation, prompt: str) -> AgentRunResult | str:
        self.calls.append((invocation, prompt))
        return self.response


def write_duplicate_functions(root: Path) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.py").write_text(
        "def calculate_a(value):\n"
        "    total = value + 1\n"
        "    doubled = total * 2\n"
        "    if doubled:\n"
        "        return doubled\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (src / "b.py").write_text(
        "def calculate_b(item):\n"
        "    result = item + 1\n"
        "    doubled = result * 2\n"
        "    if doubled:\n"
        "        return doubled\n"
        "    return 0\n",
        encoding="utf-8",
    )


class TestPromptAssembly:
    def test_finding_block_lists_every_member_and_the_fix_hint(self) -> None:
        block = format_finding_block(cross_component_group())

        assert 'Duplicate function "calculate_a"' in block
        assert "x2 copies, 5 statements each" in block
        assert "pkg_a/a.py:3" in block
        assert "pkg_b/b.py:7" in block
        assert "cross-component duplication" in block
        assert FIX_HINT in block

    def test_finding_block_notes_name_variants_and_omits_cross_component_line(self) -> None:
        block = format_finding_block(same_component_group())

        assert "cross-component" not in block

        variant_group = cross_component_group(name_variants=("calculate_alt",))
        variant_block = format_finding_block(variant_group)
        assert "calculate_alt" in variant_block

    def test_prompt_contains_constraint_paragraph_and_finding_block(self) -> None:
        prompt = build_improve_prompt(cross_component_group())

        assert format_finding_block(cross_component_group()) in prompt
        assert "Work read-only" in prompt
        assert "do not attempt to edit, create," in prompt
        assert "or delete any file" in prompt
        assert "Verify by reading the actual files before deciding" in prompt
        assert "deployment and isolation model" in prompt
        assert "would break that isolation" in prompt
        assert "patch -p0" in prompt
        assert "unified diff" in prompt
        assert "8 lines or fewer" in prompt


class TestSelectGroup:
    def test_no_groups_is_an_error(self) -> None:
        result = select_group((), None)

        assert isinstance(result, Err)
        assert "No duplicate-function groups" in result.error

    def test_default_selection_is_the_top_ranked_group(self) -> None:
        top = cross_component_group()
        rest = same_component_group()

        result = select_group((top, rest), None)

        assert result == Ok(top)

    def test_group_flag_selects_by_name(self) -> None:
        top = cross_component_group()
        rest = same_component_group("other")

        result = select_group((top, rest), "other")

        assert result == Ok(rest)

    def test_unknown_group_lists_available_names(self) -> None:
        groups = (cross_component_group(), same_component_group("other"))

        result = select_group(groups, "missing")

        assert isinstance(result, Err)
        assert 'Unknown group "missing"' in result.error
        assert "calculate_a" in result.error
        assert "other" in result.error

    def test_ambiguous_name_reports_every_matching_location(self) -> None:
        first = same_component_group("dup")
        second = ReportFunctionGroup(
            name="dup",
            statement_count=4,
            members=(("pkg2/c.py", 4), ("pkg2/d.py", 8)),
        )

        result = select_group((first, second), "dup")

        assert isinstance(result, Err)
        assert 'Ambiguous group "dup"' in result.error
        assert "pkg/a.py:1" in result.error
        assert "pkg2/c.py:4" in result.error


class TestRunImproveCommand:
    def test_diff_output_passes_through_to_stdout(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_duplicate_functions(tmp_path)

        exit_code = run_improve_command(
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            runner=FakeRunner(_DIFF),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == _DIFF
        assert 'proposing a fix for "calculate_a"' in captured.err
        assert "finished in" in captured.err

    def test_non_diff_output_exits_one_and_still_shows_raw_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_duplicate_functions(tmp_path)

        exit_code = run_improve_command(
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            runner=FakeRunner("I decline to produce a diff."),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "did not produce a reviewable diff" in captured.err
        assert "I decline to produce a diff." in captured.out

    def test_agent_error_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_duplicate_functions(tmp_path)

        exit_code = run_improve_command(
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            runner=FakeRunner(
                AgentRunResult(returncode=1, stdout="", stderr="boom")
            ),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "boom" in captured.err

    def test_output_flag_writes_the_diff_to_a_file(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_duplicate_functions(tmp_path)
        output = tmp_path / "out.diff"

        exit_code = run_improve_command(
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            output_path=str(output),
            runner=FakeRunner(_DIFF),
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert output.read_text(encoding="utf-8") == _DIFF
        assert f"Wrote proposed diff to {output}" in captured.out

    def test_no_groups_found_exits_one(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "only.py").write_text("def f():\n    return 1\n", encoding="utf-8")

        exit_code = run_improve_command(
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            runner=FakeRunner(_DIFF),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "No duplicate-function groups found" in captured.err

    def test_unknown_group_exits_one_before_invoking_the_agent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        write_duplicate_functions(tmp_path)
        runner = FakeRunner(_DIFF)

        exit_code = run_improve_command(
            group_name="does-not-exist",
            agent=ExtractAgent.CLAUDE,
            config_path=str(tmp_path / "konpy.json"),
            runner=runner,
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert 'Unknown group "does-not-exist"' in captured.err
        assert runner.calls == []
