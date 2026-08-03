# Extracting rules from prose

`konpy extract-rules` turns a prose source, such as a team style guide or agent skill, into reviewable structural and semantic rule proposals.

Extraction is explicit. `konpy check` and `konpy validate` never invoke an agent.

## Basic workflow

Start with a Markdown or text file:

```md
# Team rules

Every package directory must have a README.md.
Errors must identify the failed operation.
Mutable function defaults are forbidden.
Review service metrics weekly.
```

Run extraction:

```bash
konpy extract-rules docs/team-rules.md
```

By default, a response containing structural and semantic rules writes:

```text
packs/team-rules.json
packs/team-rules.rules.json
```

Choose either destination:

```bash
konpy extract-rules docs/team-rules.md \
  --output packs/team-style.json \
  --rules-output packs/team-style.rules.json
```

The agent run may take several minutes. Progress goes to stderr. Use `--verbose` to relay agent activity and `--timeout` to cap the subprocess.

## Four output lanes

Every source rule must enter one lane.

### Covered by existing linters

If Ruff, the active type checker, Import Linter, or pytest already owns a rule, extraction reports the existing tool instead of creating a weaker konpy approximation. See [Import boundaries](./import-boundaries.md) for why an import-architecture rule specifically routes to Import Linter rather than a konpy `importFrom*` predicate.

Example:

```json
{
  "rule": "Mutable function defaults are forbidden.",
  "tool": "ruff B006",
  "note": "Ruff checks mutable function argument defaults."
}
```

### Structural conventions

Rules expressible with konpy predicates and placeholders enter the reusable convention pack:

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

These rules can later be consumed through `conventionSources`.

### Semantic rules

Rules that need judgment but can be checked by reading one changed file enter a semantic-rules package:

```json
{
  "semanticRulesSpecVersion": "v1",
  "rules": [
    {
      "name": "contextual-errors",
      "prompt": "Verify that raised errors identify the failed operation and relevant input.",
      "match": ["src/**/*.py"],
      "source": "Errors must identify the failed operation."
    }
  ]
}
```

Wire the package into an advisory review:

```bash
konpy review \
  --agent claude \
  --match '**/*.py' \
  --rules packs/team-rules.rules.json
```

`konpy hook --rules` takes the same package if you're on the deprecated blocking command. See [Semantic rules](../reference/semantic-rules.md).

### Unmapped rules

Only checks requiring repository-wide, runtime, operational, or process knowledge stay unmapped.

Examples include:

- monitoring policy;
- release versioning decisions;
- reviewer rotation;
- production behavior that cannot be inferred from one file.

## Routing order

The extraction prompt checks each source rule against seven owners in order and stops at the first one whose scope covers the rule:

1. Ruff — lint-level concerns: style, unused imports, print/TODO markers, common security rules.
2. The active type checker — type semantics and Any policy.
3. Import Linter — resolved dependency architecture: layering, transitive forbidden imports, package independence.
4. konpy — structural conventions the supplied predicates and placeholders can express.
5. pytest — claims about runtime behavior rather than source shape.
6. Advisory review — a subjective, per-file judgment call none of the above can express; routed to the semantic lane.
7. Unmapped — anything left that needs repository-wide, runtime, operational, or process knowledge.

Owners 1, 2, 3, and 5 all land in the "covered by existing linters" lane; konpy's structural predicates never approximate a check one of them already owns.

## Reports

Without `--report`, stdout shows covered and unmapped entries. When semantic rules were written, it also prints a hook command:

```text
Wrote reusable convention proposal to packs/team-rules.json
Wrote semantic rules to packs/team-rules.rules.json
Covered by existing linters:
- Mutable function defaults are forbidden.: ruff B006 — Ruff checks mutable defaults.

Unmapped rules:
- Review service metrics weekly.: Requires runtime telemetry and a review process.

Add a PostToolUse hook: konpy hook --match '**/*.py' --rules packs/team-rules.rules.json --agent claude
```

Write the routing details to Markdown instead:

```bash
konpy extract-rules docs/team-rules.md \
  --report reports/team-rules.md
```

The report contains covered, unmapped, and semantic hook-wiring sections. Stdout only confirms the artifact paths.

## Review before use

Neither output artifact is enabled automatically.

Review the structural pack:

1. Check paths and placeholders.
2. Delete weak or duplicated conventions.
3. Confirm the predicate expresses the original rule.
4. Add accepted conventions to `conventionSources`.

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

Review semantic rules separately:

- ensure each prompt is self-contained;
- narrow broad `match` globs;
- confirm the rule can be judged from one file;
- remove rules already handled by deterministic tooling.

`extract-rules` never edits `konpy.json` or hook configuration.

## Agent selection

```bash
konpy extract-rules docs/team-rules.md --agent auto
konpy extract-rules docs/team-rules.md --agent claude
konpy extract-rules docs/team-rules.md --agent codex --model gpt-5-codex
```

`auto` checks for `claude` first, then `codex`.

The command forms are:

```bash
claude -p <prompt>
codex exec <prompt>
```

The default model is `sonnet`. Supply a Codex model explicitly when using Codex.

## Validation and write behavior

The expected agent response is:

```json
{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "semantic": [],
  "coveredElsewhere": [],
  "unmapped": []
}
```

`pack` and `unmapped` are required. The other lanes default to empty lists when omitted.

The response contract, structural pack, and semantic rules are validated before the first artifact is written.

When `semantic` is empty:

- no rules file is created;
- an existing `--rules-output` file is not changed;
- no hook-wiring hint is printed.

The structural pack is written first, followed by semantic rules and the report. A later write error leaves an already-written earlier artifact in place.

## Related workflows

[`konpy hook-propose`](./ratchet.md) uses the same four-lane output contract. Its input is logged review findings rather than a prose document.

See also:

- [Semantic rules](../reference/semantic-rules.md)
- [Import boundaries](./import-boundaries.md)
- [Agentic verification hooks](./hooks.md)
- [Reusable conventions](../reference/reusable-conventions.md)
