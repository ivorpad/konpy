"""Proposed-content reconstruction helpers for `konpy gate`."""

from __future__ import annotations

from collections.abc import Mapping

from konpy.cli._hook_support import CLAUDE_WRITE_TOOLS, HookPayload, extract_target_paths
from konpy.core.filesystem import FileSystem

__all__ = ["reconstruct_proposed_content"]


def reconstruct_proposed_content(
    payload: HookPayload,
    *,
    base: FileSystem,
) -> dict[str, str] | None:
    """Reconstruct proposed post-write file content for Claude write tools.

    Returns None when the payload cannot be reconstructed safely; callers treat
    that as fail-open allow.
    """
    if payload.tool_name not in CLAUDE_WRITE_TOOLS:
        return None

    target_paths = extract_target_paths(payload)
    if not target_paths:
        return None
    path = target_paths[0]

    if payload.tool_name == "Write":
        return _reconstruct_write(payload.tool_input, path=path)

    if payload.tool_name == "Edit":
        return _reconstruct_edit(payload.tool_input, path=path, base=base)

    if payload.tool_name == "MultiEdit":
        return _reconstruct_multi_edit(payload.tool_input, path=path, base=base)

    return None


def _reconstruct_write(tool_input: Mapping[str, object], *, path: str) -> dict[str, str] | None:
    content = tool_input.get("content")
    if not isinstance(content, str):
        return None
    return {path: content}


def _reconstruct_edit(
    tool_input: Mapping[str, object],
    *,
    path: str,
    base: FileSystem,
) -> dict[str, str] | None:
    current = _read_current_content(base=base, path=path)
    next_content = _apply_one_edit(current, tool_input)
    if next_content is None:
        return None
    return {path: next_content}


def _reconstruct_multi_edit(
    tool_input: Mapping[str, object],
    *,
    path: str,
    base: FileSystem,
) -> dict[str, str] | None:
    raw_edits = tool_input.get("edits")
    if not isinstance(raw_edits, list):
        return None

    current = _read_current_content(base=base, path=path)
    for raw_edit in raw_edits:
        if not isinstance(raw_edit, Mapping):
            return None
        next_content = _apply_one_edit(current, raw_edit)
        if next_content is None:
            return None
        current = next_content

    return {path: current}


def _read_current_content(*, base: FileSystem, path: str) -> str:
    if not base.file_exists(path):
        return ""
    return base.read_file(path)


def _apply_one_edit(current: str, raw_edit: Mapping[str, object]) -> str | None:
    old_string = raw_edit.get("old_string")
    new_string = raw_edit.get("new_string")
    if not isinstance(old_string, str) or not isinstance(new_string, str):
        return None

    if old_string == "":
        if current == "":
            return new_string
        return None

    if old_string not in current:
        return None

    replace_all = raw_edit.get("replace_all") is True
    count = -1 if replace_all else 1
    return current.replace(old_string, new_string, count)
