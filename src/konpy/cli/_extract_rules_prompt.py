"""Prompt construction for `konpy extract-rules`.

Split out of `konpy.cli.extract_rules` to keep that module under the
project's per-module line limit; `extract_rules.py` re-exports these names
under its own `__all__` so the public import path is unchanged.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from konpy.config.errors import Err, Ok, Result


def pack_contract_and_rubric() -> str:
    """Return the four-lane JSON contract and routing rubric for agent prompts."""
    return """Return exactly one JSON object with this contract and no required commentary:

{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "semantic": [
    {
      "name": "kebab-slug",
      "prompt": "self-contained verification instruction for a read-only agent inspecting one file",
      "match": ["**/*.py"],
      "source": "original rule text"
    }
  ],
  "coveredElsewhere": [
    {
      "rule": "original rule text",
      "tool": "ruff RUF012",
      "note": "why the established linter rule covers it"
    }
  ],
  "unmapped": [
    {
      "rule": "original or summarized source rule",
      "reason": "why it requires repository-wide, runtime, operational, or process knowledge"
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
- Do not edit, describe edits to, or assume edits to konpy.json. The pack
  is only a human-review proposal.

Routing order:
1. If an established Ruff or mypy rule covers the check, emit it only in
   "coveredElsewhere". Do not duplicate it with a konpy convention, including
   a weak matchContent approximation.
2. Otherwise, if the rule is expressible with the supplied konpy predicates
   and placeholders, emit it only in "pack".
3. Otherwise, if a read-only agent can verify the rule by inspecting a single
   changed file with judgment, emit it only in "semantic".
4. Only rules requiring repository-wide, runtime, operational, or process
   knowledge belong in "unmapped".

Semantic-rule requirements:
- "name" must be a kebab-case identifier containing only lowercase letters,
  digits, and hyphens.
- "prompt" must be a non-empty, self-contained verification instruction.
  It must not require the verifier to read or know the original source document.
- "match" must be a non-empty list of non-empty globs scoping the files where
  the instruction applies.
- "source" should preserve the original rule text as provenance.

Additional routing rules:
- Do not invent predicate keys.
- Ambiguous structural rules whose paths or placeholders cannot be inferred
  may be semantic only when one-file inspection is sufficient; otherwise put
  them in "unmapped" with a reason.
- Never silently drop a source rule. Every source rule must land in exactly one
  of "pack", "semantic", "coveredElsewhere", or "unmapped"."""


def build_prompt(
    *,
    source_text: str,
    source_label: str,
    predicates_reference: str,
) -> str:
    """Build the agent prompt that routes prose rules into four lanes."""
    return f"""\
You convert prose best-practices into reviewable konpy rule artifacts.

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
    source_tree_path = (
        Path(__file__).resolve().parents[3] / "docs/reference/predicates.md"
    )
    try:
        if source_tree_path.is_file():
            return Ok(source_tree_path.read_text(encoding="utf-8"))
    except OSError:
        pass

    try:
        text = (
            resources.files("konpy")
            .joinpath("_docs/reference/predicates.md")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return Err(
            "Could not read predicates reference docs/reference/predicates.md."
        )

    return Ok(text)


__all__ = [
    "build_prompt",
    "pack_contract_and_rubric",
    "read_predicates_reference",
]
