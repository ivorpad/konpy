from __future__ import annotations

from konpy.cli._gate_support import reconstruct_proposed_content
from konpy.cli._hook_support import HookPayload
from konpy.core.filesystem import FakeFileSystem


def payload(*, tool_name: str, tool_input: dict[str, object]) -> HookPayload:
    return HookPayload.model_validate(
        {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": "/project",
        }
    )


class TestReconstructProposedContent:
    def test_write_full_content(self) -> None:
        result = reconstruct_proposed_content(
            payload(
                tool_name="Write",
                tool_input={"file_path": "src/x.py", "content": "VALUE = 1\n"},
            ),
            base=FakeFileSystem(),
        )

        assert result == {"src/x.py": "VALUE = 1\n"}

    def test_write_empty_content(self) -> None:
        result = reconstruct_proposed_content(
            payload(tool_name="Write", tool_input={"file_path": "src/x.py", "content": ""}),
            base=FakeFileSystem(),
        )

        assert result == {"src/x.py": ""}

    def test_write_missing_or_non_string_content_returns_none(self) -> None:
        assert (
            reconstruct_proposed_content(
                payload(tool_name="Write", tool_input={"file_path": "src/x.py"}),
                base=FakeFileSystem(),
            )
            is None
        )
        assert (
            reconstruct_proposed_content(
                payload(
                    tool_name="Write",
                    tool_input={"file_path": "src/x.py", "content": 123},
                ),
                base=FakeFileSystem(),
            )
            is None
        )

    def test_edit_replaces_first_occurrence(self) -> None:
        base = FakeFileSystem(contents={"src/x.py": "old old\n"})

        result = reconstruct_proposed_content(
            payload(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/x.py",
                    "old_string": "old",
                    "new_string": "new",
                },
            ),
            base=base,
        )

        assert result == {"src/x.py": "new old\n"}

    def test_edit_replace_all(self) -> None:
        base = FakeFileSystem(contents={"src/x.py": "old old\n"})

        result = reconstruct_proposed_content(
            payload(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/x.py",
                    "old_string": "old",
                    "new_string": "new",
                    "replace_all": True,
                },
            ),
            base=base,
        )

        assert result == {"src/x.py": "new new\n"}

    def test_edit_on_missing_file_with_empty_old_content(self) -> None:
        result = reconstruct_proposed_content(
            payload(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/new.py",
                    "old_string": "",
                    "new_string": "created\n",
                },
            ),
            base=FakeFileSystem(),
        )

        assert result == {"src/new.py": "created\n"}

    def test_edit_old_string_not_found_returns_none(self) -> None:
        base = FakeFileSystem(contents={"src/x.py": "content\n"})

        result = reconstruct_proposed_content(
            payload(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/x.py",
                    "old_string": "missing",
                    "new_string": "new",
                },
            ),
            base=base,
        )

        assert result is None

    def test_edit_empty_old_string_against_non_empty_file_returns_none(self) -> None:
        base = FakeFileSystem(contents={"src/x.py": "content\n"})

        result = reconstruct_proposed_content(
            payload(
                tool_name="Edit",
                tool_input={
                    "file_path": "src/x.py",
                    "old_string": "",
                    "new_string": "new",
                },
            ),
            base=base,
        )

        assert result is None

    def test_multi_edit_applies_edits_in_order(self) -> None:
        base = FakeFileSystem(contents={"src/x.py": "a b c\n"})

        result = reconstruct_proposed_content(
            payload(
                tool_name="MultiEdit",
                tool_input={
                    "file_path": "src/x.py",
                    "edits": [
                        {"old_string": "a", "new_string": "x"},
                        {"old_string": "x b", "new_string": "y"},
                    ],
                },
            ),
            base=base,
        )

        assert result == {"src/x.py": "y c\n"}

    def test_multi_edit_invalid_edits_shape_returns_none(self) -> None:
        assert (
            reconstruct_proposed_content(
                payload(
                    tool_name="MultiEdit",
                    tool_input={"file_path": "src/x.py", "edits": "not-a-list"},
                ),
                base=FakeFileSystem(),
            )
            is None
        )

    def test_apply_patch_returns_none(self) -> None:
        result = reconstruct_proposed_content(
            payload(
                tool_name="apply_patch",
                tool_input={"input": "*** Update File: src/x.py\n"},
            ),
            base=FakeFileSystem(),
        )

        assert result is None

    def test_non_claude_tool_returns_none(self) -> None:
        result = reconstruct_proposed_content(
            payload(tool_name="Bash", tool_input={"command": "ls"}),
            base=FakeFileSystem(),
        )

        assert result is None
