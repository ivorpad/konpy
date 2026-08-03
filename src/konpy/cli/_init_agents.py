"""`konpy init --agents` implementation: scaffold the agent-loop wiring in one command.

Extends the plain `konpy init` starter config with the artifacts a repo needs
to run konpy from Claude Code hooks: a `verify` roster appended to
`konpy.json`, a generated-guidance block in `AGENTS.md` (rendered through the
same in-process machinery `konpy explain` uses), a `konpy gate`/`konpy
review` hook wiring in `.claude/settings.json`, and a `.gitignore` entry for
`.konpy/`. Every artifact is created only if absent; appending to an
existing `.gitignore` is the one exception where an existing file is edited.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import typer

from konpy.cli.init import INIT_TEMPLATE
from konpy.config.errors import Err, Ok, Result
from konpy.config.loader import CONFIG_FILENAME, load_config_runtime
from konpy.core.explain import render_explain

_CLAUDE_SETTINGS_TEMPLATE = (
    resources.files("konpy")
    .joinpath("cli/_init_claude_settings_template.json")
    .read_text(encoding="utf-8")
)

_AGENTS_MD_RELATIVE_PATH = "AGENTS.md"
_CLAUDE_SETTINGS_RELATIVE_PATH = ".claude/settings.json"
_GITIGNORE_RELATIVE_PATH = ".gitignore"
_HOOK_DOCS_POINTER = "docs/guides/claude-code-hook.md"

_GUIDANCE_START_MARKER = "<!-- konpy:generated-guidance:start -->"
_GUIDANCE_END_MARKER = "<!-- konpy:generated-guidance:end -->"

_AGENTS_MD_INTRO = (
    "Conventions for agents working in this repository; the marked block "
    "is generated from konpy.json."
)

_GITIGNORE_ENTRY = ".konpy/"

_NEXT_STEPS = """\
Next steps:
  konpy check                   run the conventions against this codebase
  konpy check --write-baseline  baseline violations, then tighten konpy gate with --fail-closed
  See docs/guides/claude-code-hook.md for how the scaffolded hooks fit together."""


@dataclass(frozen=True, kw_only=True)
class _ArtifactOutcome:
    """What happened to one scaffolded artifact, and the summary line to print for it."""

    changed: bool
    line: str


def _verify_section_text() -> str:
    """Return `INIT_TEMPLATE` with a minimal `verify` roster appended.

    Splices the new section in after the closing brace of `unusedCode`
    rather than round-tripping through `json.loads`/`json.dumps`, so the
    rest of the starter template's hand-authored formatting is untouched.
    """
    base = INIT_TEMPLATE.rstrip("\n")
    if not base.endswith("}"):
        raise ValueError("_init_template.json does not end with a closing brace")
    body = base[:-1].rstrip()
    return (
        f"{body},\n"
        '  "verify": {\n'
        '    "steps": [\n'
        '      { "name": "konpy-validate", "run": ["konpy", "validate"] },\n'
        '      { "name": "konpy-check", "run": ["konpy", "check"] }\n'
        '    ]\n'
        "  }\n"
        "}\n"
    )


def _write_konpy_json(target_dir: Path) -> _ArtifactOutcome:
    """Write the starter `konpy.json` plus its `verify` roster, unless one exists."""
    path = target_dir / CONFIG_FILENAME
    if path.exists():
        return _ArtifactOutcome(changed=False, line=f"skipped (exists): {CONFIG_FILENAME}")

    path.write_text(_verify_section_text(), encoding="utf-8")
    return _ArtifactOutcome(
        changed=True,
        line=f"Wrote {CONFIG_FILENAME} (strict starter, plus a verify roster: "
        "konpy-validate, konpy-check).",
    )


def _render_agents_md_guidance(target_dir: Path) -> Result[str]:
    """Render AGENTS.md's full text from `target_dir`'s konpy.json, in-process.

    Uses the same `load_config_runtime` + `render_explain` path `konpy
    explain` uses, so the generated block can never drift from what `konpy
    explain` would print for this config.
    """
    loaded_result = load_config_runtime(config_path=target_dir / CONFIG_FILENAME)
    if isinstance(loaded_result, Err):
        return loaded_result

    rendered = render_explain(
        loaded_result.value.config,
        format="md",
        predicate_registry=loaded_result.value.predicate_registry,
    ).rstrip("\n")
    comment = (
        f"<!-- Generated from {CONFIG_FILENAME} by `konpy init --agents`. "
        "Do not edit by hand. -->"
    )
    block = f"{_GUIDANCE_START_MARKER}\n{comment}\n{rendered}\n{_GUIDANCE_END_MARKER}"
    return Ok(f"{_AGENTS_MD_INTRO}\n\n{block}\n")


def _write_agents_md(target_dir: Path) -> _ArtifactOutcome:
    """Write AGENTS.md's generated-guidance block, unless the file already exists."""
    path = target_dir / _AGENTS_MD_RELATIVE_PATH
    if path.exists():
        return _ArtifactOutcome(changed=False, line=f"skipped (exists): {_AGENTS_MD_RELATIVE_PATH}")

    rendered_result = _render_agents_md_guidance(target_dir)
    if isinstance(rendered_result, Err):
        return _ArtifactOutcome(
            changed=False,
            line=f"skipped (could not render guidance from {CONFIG_FILENAME}): "
            f"{_AGENTS_MD_RELATIVE_PATH} -- {rendered_result.error}",
        )

    path.write_text(rendered_result.value, encoding="utf-8")
    return _ArtifactOutcome(
        changed=True,
        line=f"Wrote {_AGENTS_MD_RELATIVE_PATH} (guidance block generated from {CONFIG_FILENAME}).",
    )


def _write_claude_settings(target_dir: Path) -> _ArtifactOutcome:
    """Write `.claude/settings.json`'s gate/review hook wiring, unless it already exists."""
    path = target_dir / _CLAUDE_SETTINGS_RELATIVE_PATH
    if path.exists():
        return _ArtifactOutcome(
            changed=False,
            line=f"skipped (exists): {_CLAUDE_SETTINGS_RELATIVE_PATH} -- merge the hooks by "
            f"hand, see {_HOOK_DOCS_POINTER}",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CLAUDE_SETTINGS_TEMPLATE, encoding="utf-8")
    return _ArtifactOutcome(
        changed=True,
        line=f"Wrote {_CLAUDE_SETTINGS_RELATIVE_PATH} "
        "(PreToolUse konpy gate, PostToolUse konpy review).",
    )


def _update_gitignore(target_dir: Path) -> _ArtifactOutcome:
    """Append `.konpy/` to an existing `.gitignore` if it lacks it; never creates one."""
    path = target_dir / _GITIGNORE_RELATIVE_PATH
    if not path.exists():
        return _ArtifactOutcome(
            changed=False,
            line=f"skipped (no {_GITIGNORE_RELATIVE_PATH}): {_GITIGNORE_ENTRY} not added",
        )

    current = path.read_text(encoding="utf-8")
    already_present = any(
        line.strip() == _GITIGNORE_ENTRY or line.strip() == _GITIGNORE_ENTRY.rstrip("/")
        for line in current.splitlines()
    )
    if already_present:
        return _ArtifactOutcome(
            changed=False,
            line=f"skipped (already present): {_GITIGNORE_RELATIVE_PATH} already ignores "
            f"{_GITIGNORE_ENTRY}",
        )

    separator = "" if current == "" or current.endswith("\n") else "\n"
    path.write_text(f"{current}{separator}{_GITIGNORE_ENTRY}\n", encoding="utf-8")
    return _ArtifactOutcome(
        changed=True,
        line=f"Updated {_GITIGNORE_RELATIVE_PATH} (added {_GITIGNORE_ENTRY}).",
    )


def run_init_agents_command() -> int:
    """Scaffold the agent-loop wiring into the current directory.

    Writes (only if absent) a `konpy.json` verify roster, `AGENTS.md`'s
    generated-guidance block, `.claude/settings.json`'s gate/review hooks,
    and appends `.konpy/` to an existing `.gitignore`. Exits `0` if at least
    one artifact was created or the `.gitignore` was updated, `1` if
    everything was already in place.
    """
    target_dir = Path.cwd()

    outcomes = [
        _write_konpy_json(target_dir),
        _write_agents_md(target_dir),
        _write_claude_settings(target_dir),
        _update_gitignore(target_dir),
    ]

    for outcome in outcomes:
        typer.echo(outcome.line)

    typer.echo(_NEXT_STEPS)

    return 0 if any(outcome.changed for outcome in outcomes) else 1


__all__ = ["run_init_agents_command"]
