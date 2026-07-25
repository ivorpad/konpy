"""Physical line counting shared by the report, predicates, and infer.

One definition of "how many physical lines does this text have" so the
report's LOC banner, `restrictFileLength`'s violation count, and the
file-length infer heuristic can never drift on edge cases.
"""

from __future__ import annotations


def count_physical_lines(source: str) -> int:
    """Count physical lines; a trailing newline does not add a phantom line."""
    if not source:
        return 0
    return source.count("\n") + (0 if source.endswith("\n") else 1)


__all__ = ["count_physical_lines"]
