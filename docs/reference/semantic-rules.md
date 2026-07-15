# Semantic rules

Semantic rules are single-file checks that need judgment rather than a structural predicate. They are consumed by `konpy hook --rules FILE`.

Examples include:

- whether an error message gives enough context;
- whether a docstring matches the implementation;
- whether logs expose sensitive data;
- whether request and response models are kept separate.

Semantic rules are not part of `konpy.json`. They cannot be loaded through `conventionSources`, and they do not appear in `konpy.schema.json`.

## File format

A semantic-rules package uses this shape:

```json
{
  "semanticRulesSpecVersion": "v1",
  "rules": [
    {
      "name": "contextual-errors",
      "prompt": "Verify that raised errors identify the failed operation and relevant input.",
      "match": ["src/**/*.py"],
      "source": "Errors must contain useful context."
    }
  ]
}
```

### Package fields

| Field | Required | Meaning |
| --- | --- | --- |
| `semanticRulesSpecVersion` | yes | Package version. The current value is `"v1"`. |
| `rules` | yes | List of semantic rules. The list may be empty. |

### Rule fields

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Lowercase identifier matching `[a-z0-9-]+`. Verdicts and findings use this name. |
| `prompt` | yes | Non-empty verification instruction for a read-only agent inspecting one file. |
| `match` | yes | Non-empty list of non-empty globs selecting files for this rule. |
| `source` | no | Original rule text or other provenance. It is not sent to the verifier. |

Unknown fields are rejected.

A rule prompt must be self-contained. It must not require the verifier to read the source document used by `extract-rules`.

## Four-lane routing

`konpy extract-rules` and `konpy hook-propose` route each source rule into one lane:

1. **Covered elsewhere:** an established Ruff or mypy rule already checks it.
2. **Structural:** built-in konpy predicates and placeholders can express it.
3. **Semantic:** a read-only agent can judge it by inspecting one changed file.
4. **Unmapped:** it needs repository-wide, runtime, operational, or process knowledge.

Each source rule belongs in one lane. Established Ruff or mypy checks should not be recreated as weak `matchContent` conventions.

Structural rules are written as a [`ReusableConventionsPackageV1`](./reusable-conventions.md). Semantic rules are written as the package described on this page. Covered and unmapped rules appear in the routing report.

## Running semantic rules

Run the hook with a semantic-rules package:

```bash
konpy hook \
  --agent claude \
  --match 'src/**/*.py' \
  --rules packs/team-style.rules.json
```

`--match` is the hook-level prefilter. After a target path passes that filter, konpy selects rules whose own `match` globs match the path.

If no semantic rule applies, the hook exits `0` without resolving or spawning the agent.

## Batched verification

All applicable rules for one file are sent in one verifier prompt. Ten matching rules still produce one agent call for that file.

A write payload containing several files produces at most one call per applicable file. Files are processed in payload order. Rules appear in package order.

The verifier returns:

```json
{
  "verdict": "pass",
  "failures": []
}
```

or:

```json
{
  "verdict": "fail",
  "failures": [
    {
      "rule": "contextual-errors",
      "reasons": [
        "The ValueError does not identify which account operation failed."
      ]
    }
  ]
}
```

Only names of rules applicable to the current file are accepted.

Duplicate failure entries are merged. Duplicate reasons are removed. Output is reordered to package order.

A fail verdict without failures receives a synthesized reason for the first applicable rule. A named failure without reasons receives the same fallback:

```text
Verification failed for src/service.py without a rule-specific reason.
```

## Output and exit codes

Failed reasons are written to stderr:

```text
contextual-errors: The ValueError does not identify which account operation failed.
```

| Exit | Meaning |
| --- | --- |
| `0` | Pass, or skip because no tool, path, or semantic rule applies. |
| `1` | Configuration or infrastructure failure, including an invalid rules file or invalid verifier response. |
| `2` | Verified semantic-rule failure. |

Exit `2` is reserved for verified failures.

## Findings and promotion

With `--log`, rules mode writes one `HookFinding` per failed rule:

```json
{
  "schemaVersion": "v1",
  "verdict": "fail",
  "filePath": "src/service.py",
  "prompt": "Verify that raised errors identify the failed operation and relevant input.",
  "rule": "contextual-errors",
  "agent": "claude",
  "model": "sonnet",
  "reasons": [
    "The ValueError does not identify which account operation failed."
  ]
}
```

The stored `prompt` is the individual rule prompt, not the combined verifier prompt. `hook-propose` continues grouping findings by exact prompt, so different semantic rules promote independently.

The `rule` field is optional. Older single-prompt findings remain readable.

## Relationship to reusable conventions

Reusable conventions are deterministic structural checks consumed through `konpy.json`. Semantic rules are agent instructions consumed only by `konpy hook --rules`.

Use reusable conventions when a predicate can express the check. Use semantic rules when one-file inspection is enough but judgment is required.

See also:

- [Reusable conventions](./reusable-conventions.md)
- [Reusable packs](./packs.md)
- [Extracting rules from prose](../guides/extracting-rules.md)
- [Agentic verification hooks](../guides/hooks.md)
- [The ratchet](../guides/ratchet.md)
