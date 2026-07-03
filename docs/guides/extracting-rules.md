# Extracting rules from prose

`konpy extract-rules` turns a prose source — such as a team style guide, an internal checklist, or an agent skill file — into a reviewable reusable-convention pack proposal.

Extraction is always explicit. `konpy check` and `konpy validate` never invoke an agent.

## Basic workflow

Start with a markdown or text file:

```md
# Team rules

Every package directory must have a README.md.
Python modules should use Ruff formatting.
```

Run extraction:

```bash
konpy extract-rules docs/team-rules.md
```

By default this writes:

```text
packs/team-rules.json
```

You can choose the destination:

```bash
konpy extract-rules docs/team-rules.md -o packs/team-style.json
```

The generated file is a [`ReusableConventionsPackageV1`](../reference/reusable-conventions.md) proposal:

```json
{
  "conventionSpecVersion": "v1",
  "conventions": [
    {
      "name": "package-dir-must-have-readme",
      "description": "Every package directory must have a README.md file.",
      "paths": "packages/*",
      "must": {
        "haveFiles": ["README.md"]
      }
    }
  ]
}
```

## Review before use

The generated pack is not automatically enabled.

After extraction:

1. Open the generated JSON.
2. Check that every convention is meaningful for your repository.
3. Delete or rewrite over-broad rules.
4. Check the unmapped-rules output.
5. Only after review, manually add the pack to `conventionSources`.

Example:

```json
{
  "version": "v1",
  "conventionSources": {
    "team": "./packs/team-style.json"
  },
  "conventions": [
    "team/package-dir-must-have-readme"
  ]
}
```

`extract-rules` never edits `konpy.json` for you.

Sibling workflow: [`konpy hook-propose`](ratchet.md) uses the same reviewable-pack idea, but its input is logged `konpy hook` fail findings instead of a prose source file.

## Agent selection

The command shells out to a local agent CLI.

```bash
konpy extract-rules docs/team-rules.md --agent auto
konpy extract-rules docs/team-rules.md --agent claude
konpy extract-rules docs/team-rules.md --agent codex
```

`--agent auto` is the default. It selects the first available binary on `PATH`:

1. `claude`
2. `codex`

`--model` pins the model the agent CLI runs on (forwarded as its own `--model` flag). The default is `sonnet` — a Claude model name, so pass an explicit `--model` when the resolved agent is `codex`.

The invocation forms are:

```bash
claude -p <prompt>
codex exec <prompt>
```

If neither binary is found, the command exits with an error naming both `claude` and `codex`.

## Unmapped rules

The extraction prompt tells the agent not to silently drop rules. Anything that cannot be expressed with `konpy` predicates should be returned as unmapped.

Without `--report`, unmapped rules are printed to stdout:

```bash
konpy extract-rules docs/team-rules.md
```

With `--report`, they are written to a Markdown file:

```bash
konpy extract-rules docs/team-rules.md --report unmapped-rules.md
```

Typical unmapped rules include:

- formatting rules, which belong in Ruff;
- type-checking rules, which belong in mypy or pyright;
- pytest behavior rules;
- in-function lint rules;
- review-process guidance;
- rules that need project-specific context the source did not provide;
- broad design advice that cannot be checked structurally.

Use the unmapped list as a follow-up checklist. Some items may belong in another tool; others may need a custom plugin predicate or a hand-written convention.

## What can be mapped

`konpy` is best at structural repository rules:

- files or directories must exist;
- matched paths must be files or directories;
- modules must export, declare, or import specific symbols;
- imports must or must not come from specific sources;
- barrels must remain pure re-export modules;
- files must contain simple regex-matched content;
- public functions/classes should have docstrings or annotations;
- source files should have paired test files.

The agent prompt includes the full [predicate reference](../reference/predicates.md), so generated rules should use the same vocabulary as hand-written conventions.

## Validation before write

The agent must return one JSON object with this shape:

```json
{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "unmapped": []
}
```

`konpy` validates `pack` with the reusable-conventions schema before writing. If validation fails, the command exits non-zero and writes nothing.

This means a generated file is at least schema-valid, but it still needs human review.
