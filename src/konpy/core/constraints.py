"""Placeholder constraints: ``{name:matches(regex)}`` / ``{name:segments(n)}``.
Port of core/placeholder-constraint.ts and core/constraints/. Unknown
constraint names validate permissively (return True). Regexes use Python
``re`` — see docs for the (small) divergence surface from JS RegExp.
"""

import re
from dataclasses import dataclass

from konpy.core.case_utils import split_words

_CONSTRAINT_REGEX = re.compile(r"^([a-zA-Z][a-zA-Z0-9]*)(?:\((.*)\))?$")


@dataclass(frozen=True)
class PlaceholderConstraint:
    """A parsed ``name(arg)`` placeholder constraint."""

    name: str
    arg: str | None = None


def parse_placeholder_constraint(raw: str) -> PlaceholderConstraint | None:
    """Parse a ``name`` or ``name(arg)`` constraint string, or None if malformed."""
    match = _CONSTRAINT_REGEX.match(raw)
    if match is None:
        return None
    return PlaceholderConstraint(name=match.group(1), arg=match.group(2))


def validate_matches_constraint(value: str, arg: str | None) -> bool:
    """Check whether `value` matches the `arg` regex."""
    if arg is None:
        return False
    try:
        regex = re.compile(arg)
    except re.error:
        return False
    return regex.search(value) is not None


def validate_segments_constraint(value: str, arg: str | None) -> bool:
    """Check whether `value` has exactly `arg` word segments."""
    if arg is None:
        return False
    stripped = arg.strip()
    if not stripped:
        return False
    try:
        expected = float(stripped)
    except ValueError:
        return False
    if not expected.is_integer() or expected < 1:
        return False
    return len(split_words(value)) == int(expected)


def validate_placeholder_constraint(value: str, constraint: PlaceholderConstraint) -> bool:
    """Dispatch `constraint` to its validator; unknown constraint names pass permissively."""
    match constraint.name:
        case "segments":
            return validate_segments_constraint(value, constraint.arg)
        case "matches":
            return validate_matches_constraint(value, constraint.arg)
        case _:
            return True
