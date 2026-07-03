"""Prompt construction for `konsistent extract-rules`.

Split out of `konsistent.cli.extract_rules` to keep that module under the
project's per-module line limit; `extract_rules.py` re-exports these names
under its own `__all__` so the public import path is unchanged.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from konsistent.config.errors import Err, Ok, Result


def pack_contract_and_rubric() -> str:
    """Return the reusable-pack JSON contract and mappability rubric for agent prompts."""
    return """Return exactly one JSON object with this contract and no required commentary:

{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "unmapped": [
    {
      "rule": "original or summarized source rule",
      "reason": "why it cannot be represented with konsistent predicates"
    }
  ]
}

The "pack" value must validate as ReusableConventionsPackageV1.

ReusableConventionsPackageV1 format summary:
- Top-level object: {"conventionSpecVersion": "v1", "conventions": [...]}.
- Each convention requires "name" and "description".
- Each convention may include "severity", "paths", "excludeFiles", "if", "for",
  "must", and "mustNot".
- Each convention must include at least one of "must" or "mustNot".
- Reusable conventions only allow flat object-form "must" and "mustNot".
- Do not emit MustBlock[] arrays in reusable conventions.
- Do not edit, describe edits to, or assume edits to konsistent.json. The pack
  is only a human-review proposal.

Mappability rubric:
- Map only rules expressible with the predicates and placeholders in the
  predicates reference below.
- Do not invent predicate keys.
- Rules about formatting, Ruff, mypy, pytest behavior, in-function linting,
  process advice, review workflow, dependency choices, runtime performance,
  or broad design judgment should be reported in "unmapped".
- Ambiguous or project-specific rules whose paths/placeholders cannot be
  inferred should be reported in "unmapped" with a reason.
- Never silently drop a source rule. If a rule cannot be mapped, list it in
  "unmapped"."""


def build_prompt(
    *,
    source_text: str,
    source_label: str,
    predicates_reference: str,
) -> str:
    """Build the agent prompt that converts prose rules into a reusable pack."""
    return f"""\
You convert prose best-practices into a reviewable konsistent reusable convention pack.

{pack_contract_and_rubric()}

Source file: {source_label}

--- SOURCE TEXT START ---
{source_text}
--- SOURCE TEXT END ---

--- FULL docs/reference/predicates.md START ---
{predicates_reference}
--- FULL docs/reference/predicates.md END ---
"""


def read_predicates_reference() -> Result[str]:
    """Read `docs/reference/predicates.md` from the source tree or package data."""
    source_tree_path = Path(__file__).resolve().parents[3] / "docs/reference/predicates.md"
    try:
        if source_tree_path.is_file():
            return Ok(source_tree_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    try:
        text = (
            resources.files("konsistent")
            .joinpath("_docs/reference/predicates.md")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return Err("Could not read predicates reference docs/reference/predicates.md.")

    return Ok(text)


__all__ = ["build_prompt", "pack_contract_and_rubric", "read_predicates_reference"]
