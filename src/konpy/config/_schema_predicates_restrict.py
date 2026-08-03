"""Options models for the wildcard-matching ``restrict*`` predicates.

``restrictDecorators``/``restrictBaseClasses``/``restrictCalls``/
``restrictImports`` share a `forbid`/`allow` star-pattern shape. Split out of
``_schema_predicates.py`` to keep that module under the 300-line cap.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from konpy.config._schema_types import NonEmptyString, _StrictModel


class RestrictDecoratorsOptionsV1(_StrictModel):
    """Options for the ``restrictDecorators`` predicate."""

    forbid: list[NonEmptyString] = Field(
        min_length=1,
        description="Star-pattern decorator paths to forbid (written or resolved form).",
    )
    allow: list[NonEmptyString] | None = Field(
        default=None,
        min_length=1,
        description="Star-pattern decorator paths that override a forbid match.",
    )


class RestrictBaseClassesOptionsV1(_StrictModel):
    """Options for the ``restrictBaseClasses`` predicate."""

    forbid: list[NonEmptyString] = Field(
        min_length=1,
        description="Star-pattern base class paths to forbid (written or resolved form).",
    )
    allow: list[NonEmptyString] | None = Field(
        default=None,
        min_length=1,
        description="Star-pattern base class paths that override a forbid match.",
    )


class RestrictCallsOptionsV1(_StrictModel):
    """Options for the ``restrictCalls`` predicate."""

    forbid: list[NonEmptyString] = Field(
        min_length=1,
        description="Star-pattern callee paths to forbid (written or resolved form).",
    )
    allow: list[NonEmptyString] | None = Field(
        default=None,
        min_length=1,
        description="Star-pattern callee paths that override a forbid match.",
    )
    scope: Literal["any", "module"] = Field(
        default="any",
        description=(
            'When "module", only check call sites that run at import time: module-level '
            "statements and class-body statements (class bodies execute when the class "
            'is defined). When "any", check calls at every scope, including inside '
            "function bodies."
        ),
    )


class RestrictImportsOptionsV1(_StrictModel):
    """Options for the ``restrictImports`` predicate."""

    forbid: list[NonEmptyString] = Field(
        min_length=1,
        description="Star-pattern import paths to forbid, matched against the import's "
        "source module or its full symbol path.",
    )
    allow: list[NonEmptyString] | None = Field(
        default=None,
        min_length=1,
        description="Star-pattern import paths that override a forbid match.",
    )
    scope: Literal["any", "module", "function"] = Field(
        default="any",
        description=(
            'Restrict which imports are checked by where they execute: "module" for '
            'top-level imports only, "function" for imports nested inside a function '
            'body only, or "any" for both.'
        ),
    )
    includeTypeChecking: bool = Field(
        default=False,
        description=(
            "When false (the default), imports guarded by `if TYPE_CHECKING:` are "
            "skipped. Set true to check them too."
        ),
    )


__all__ = [
    "RestrictBaseClassesOptionsV1",
    "RestrictCallsOptionsV1",
    "RestrictDecoratorsOptionsV1",
    "RestrictImportsOptionsV1",
]
