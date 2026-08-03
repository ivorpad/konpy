# The ratchet: from agentic findings to rule proposals

## The loop

The ratchet turns review findings into reviewable proposals:

1. `konpy review --log` records findings.
2. `konpy hook-propose` groups recurring prompts.
3. The proposal agent routes them into structural, semantic, covered, and unmapped lanes.
4. A human reviews each artifact.
5. Accepted structural rules enter `konpy.json`; accepted semantic rules remain in a `review --rules` package.

A model's opinion never promotes itself: no step here is automatic, and no finding blocks anything on its own. Not every semantic rule can become deterministic, either — a recurring finding may remain semantic if no structural predicate expresses it.

## A second ratchet: the baseline file

The loop above needs an agent to run at all. `konpy check --write-baseline` needs none: it's a deterministic ratchet for turning on a rule, or a whole stricter config, against code that already violates it, without touching a line of source or waiting on a review pass.

Brownfield flow: adopt the strict config, record its current violations, commit the baseline, wire CI to the pair.

```bash
konpy check --config-path konpy.strict.json --write-baseline --baseline konpy.strict.baseline.json
git add konpy.strict.json konpy.strict.baseline.json
```

CI then runs:

```bash
konpy check --config-path konpy.strict.json --baseline konpy.strict.baseline.json
```

and fails only on violations the baseline didn't already know about. Fix debt at your own pace; each fix leaves its `(file, convention)` baseline entry stale, and `check` prints a warning naming it, not a failure, since penalizing the moment debt goes down would be backwards. Run `--write-baseline` again to lower the floor and clear the warning.

Neither ratchet can raise the bar silently. A baseline that would need a higher count than what's recorded prints `baseline: raised <file>/<convention> from X to Y` on `--write-baseline`, the same way a `hook-propose` pack never installs itself into `konpy.json`. The two compose: the baseline adopts a rule cleanly on day one against code you haven't touched yet; the findings-log loop above discovers rules you don't have at all.

Full flag reference: [`check`, Baseline and the ratchet](../reference/cli.md#baseline-and-the-ratchet).

## Turning on logging

Prompt mode:

```bash
konpy review \
  --agent claude \
  --match 'src/**/*.py' \
  --prompt 'Verify that docstrings match implemented behavior.' \
  --log .konpy/hook-findings.jsonl
```

Rules mode:

```bash
konpy review \
  --agent claude \
  --match '**/*.py' \
  --rules packs/team-style.rules.json \
  --log .konpy/hook-findings.jsonl
```

`konpy hook --log` writes the same log if you're still on the deprecated blocking command — just swap `review` for `hook` above.

Logging is fail-open either way. `review` never turns a finding into a nonzero exit (`0` pass/skip/finding, `1` local misconfiguration only); the deprecated `hook` still reserves exit `2` for a fail verdict.

A log write error is printed after verifier feedback, named after whichever command produced it:

```text
konpy review: --log warning: <detail>
konpy hook: --log warning: <detail>
```

## HookFinding JSONL schema

Each line is one JSON object.

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Record version, currently `"v1"` |
| `verdict` | Persisted verdict, currently `"fail"` |
| `loggedAt` | UTC ISO-8601 timestamp |
| `sessionId` | Optional host session identifier |
| `cwd` | Optional host working directory |
| `toolName` | Optional write tool name |
| `filePath` | Failed file |
| `prompt` | Verification prompt used for promotion grouping |
| `rule` | Optional semantic rule name |
| `agent` | Verifier CLI |
| `model` | Verifier model |
| `reasons` | Non-empty list of failure reasons |

An old prompt-mode record can omit `rule`:

```json
{"schemaVersion":"v1","verdict":"fail","filePath":"src/service.py","prompt":"Verify docstrings match behavior.","agent":"claude","model":"sonnet","reasons":["The docstring overstates the implementation."]}
```

A rules-mode record stores the failed rule's own prompt and name:

```json
{"schemaVersion":"v1","verdict":"fail","filePath":"src/service.py","prompt":"Verify that errors identify the failed operation.","rule":"contextual-errors","agent":"claude","model":"sonnet","reasons":["The ValueError omits the failed operation."]}
```

The batched verifier prompt is not persisted. This keeps promotion groups tied to individual semantic rules.

Readers ignore unknown fields, so newer records remain compatible with older tooling.

## Rules-mode logging

A rules verdict may fail several rules for one file. konpy appends one finding per failed rule.

Given:

```json
{
  "verdict": "fail",
  "failures": [
    {
      "rule": "contextual-errors",
      "reasons": ["The ValueError omits the operation."]
    },
    {
      "rule": "honest-docstrings",
      "reasons": ["The docstring claims persistence that is absent."]
    }
  ]
}
```

the log receives two lines.

Prompt mode still records one finding for the first failed path.

## Running `hook-propose`

The default input and outputs are:

```text
.konpy/hook-findings.jsonl
packs/hook-proposals.json
packs/hook-proposals.rules.json
```

The semantic file is written only when the proposed semantic lane is non-empty.

Run with defaults:

```bash
konpy hook-propose
```

Choose all artifact paths:

```bash
konpy hook-propose .konpy/hook-findings.jsonl \
  --output packs/ratcheted-conventions.json \
  --rules-output packs/ratcheted.rules.json \
  --report reports/ratchet-routing.md
```

Select an agent:

```bash
konpy hook-propose --agent claude --model sonnet
konpy hook-propose --agent codex --model gpt-5-codex --timeout 600
```

`auto` prefers Claude, then Codex.

## Aggregation

Findings are grouped by exact `prompt`.

The optional `rule` field does not change grouping. Two findings with different rule names but identical prompts enter the same group. Two semantic rules with different prompts remain separate.

Within each group:

- occurrences are counted;
- file paths are deduplicated in first-seen order;
- reasons are deduplicated in first-seen order;
- samples are capped before prompt construction.

## Four-lane promotion

The proposal agent returns:

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

A finding may become:

- a structural reusable convention;
- a semantic rule that remains in `review` (or `hook`) verification;
- a Ruff, type-checker, or Import Linter recommendation;
- an unmapped item when the evidence is insufficient or the rule needs broader context.

The evidence rubric treats a single occurrence as weak evidence unless its reasons identify a clear general pattern.

## Output and failure behavior

Without `--report`, stdout prints covered and unmapped entries plus a semantic wiring command when applicable.

With `--report`, the Markdown report contains those details and stdout only confirms artifact paths.

Exit codes:

| Exit | Meaning |
| --- | --- |
| `0` | Proposal succeeded, or no valid findings were present |
| `1` | Read, agent, contract, schema, path, or write failure |

A missing findings file produces a calm no-findings message and no agent call.

The pack is written first. A later semantic or report write failure leaves the pack in place.

## Review workflow

Review the structural pack and semantic rules separately.

For a structural proposal:

1. Confirm the paths and predicates match the evidence.
2. Remove rules already handled by Ruff, your type checker, or Import Linter.
3. Add accepted rules through `conventionSources`.

For a semantic proposal:

1. Confirm the prompt can be judged from one file.
2. Narrow the `match` globs.
3. Keep the prompt self-contained.
4. Add the rules package to the `review` command.

Example structural wiring:

```json
{
  "version": "v1",
  "conventionSources": {
    "ratchet": "./packs/ratcheted-conventions.json"
  },
  "conventions": [
    "ratchet/service-modules-export-matching-class"
  ]
}
```

Example semantic wiring:

```bash
konpy review \
  --agent claude \
  --match '**/*.py' \
  --rules packs/ratcheted.rules.json
```

`hook-propose` never edits `konpy.json` or the hook/review wiring.

## Suppressions

The promotion prompt rejects proposals that create or recommend `# konpy: ignore[...]` comments.

Suppressions require explicit human approval under the [suppression consent policy](../reference/suppressions.md).

## See also

- [Semantic rules](../reference/semantic-rules.md)
- [Agentic verification hooks](./hooks.md)
- [Extracting rules from prose](./extracting-rules.md)
- [Reusable conventions](../reference/reusable-conventions.md)
