# The ratchet: from agentic findings to deterministic conventions

## The loop

The ratchet loop turns repeated agentic feedback into deterministic checks: `konpy hook --log` observes verified agentic failures, `konpy hook-propose` mines the log into a reviewable `ReusableConventionsPackageV1` pack plus an unmapped report, a human reviews the proposal and wires survivors into `konpy.json` via `conventionSources`, and deterministic checking (`konpy check --files`, including the [`claude-code-hook.md`](./claude-code-hook.md) recipe) enforces them forever without a model. Each promotion shrinks the slice of review that needs an agent.

## Turning on logging

Add `--log .konpy/hook-findings.jsonl` to the agentic hook command from [Agentic verification hooks](./hooks.md):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "konpy hook --agent claude --model sonnet --match 'src/**/*.py' --prompt 'Check that this module defines what it claims to: class and function names match their bodies, docstrings are not aspirational.' --log .konpy/hook-findings.jsonl"
          }
        ]
      }
    ]
  }
}
```

Logging is fail-open and never changes the hook exit-code contract: `0` still means pass or skipped, `1` still means infra fail-open, and `2` still means a verified fail verdict. If writing the log fails, the hook still exits `2`; after the normal reason lines, stderr gets one extra warning line prefixed with:

```text
konpy hook: --log warning:
```

Only verified `fail` verdicts are logged. Pass verdicts, skipped hook invocations, malformed payloads, agent subprocess failures, and unparseable agent output are not logged. Because `konpy hook` returns immediately on the first failing matched path, each hook invocation logs at most one finding: the first failing path.

## HookFinding JSONL schema

The log is newline-delimited JSON. Each line is one `HookFinding`.

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Log record schema version. Currently always `"v1"`. |
| `verdict` | Persisted verdict. Currently only `"fail"` records are valid promotion input. |
| `loggedAt` | UTC ISO-8601 timestamp for when the finding was written. |
| `sessionId` | Optional hook-session identifier from the host payload. |
| `cwd` | Optional working directory from the host payload. |
| `toolName` | Optional write tool name, such as `Write`, `Edit`, `MultiEdit`, or `apply_patch`. |
| `filePath` | Matched file path that failed verification. |
| `prompt` | Exact natural-language verification prompt passed to `konpy hook`. |
| `agent` | Verifier agent used by the hook, such as `claude` or `codex`. |
| `model` | Model value forwarded to the verifier agent. |
| `reasons` | Non-empty list of concrete fail reasons returned by the verifier. |

Example line:

```json
{"schemaVersion":"v1","verdict":"fail","loggedAt":"2026-07-03T12:34:56.789012+00:00","cwd":"/repo","toolName":"Write","filePath":"src/service.py","prompt":"Docstrings are not aspirational.","agent":"claude","model":"sonnet","reasons":["Function docstring claims persistence, but the implementation only validates input."]}
```

## Running `hook-propose`

By default, `hook-propose` reads `.konpy/hook-findings.jsonl` and writes `packs/hook-proposals.json`:

```bash
konpy hook-propose
```

Pass an explicit findings log:

```bash
konpy hook-propose .konpy/hook-findings.jsonl
```

Choose output and report paths:

```bash
konpy hook-propose .konpy/hook-findings.jsonl \
  -o packs/ratcheted-conventions.json \
  --report reports/hook-unmapped.md
```

Choose the proposal agent and model:

```bash
konpy hook-propose --agent claude --model sonnet
konpy hook-propose --agent codex --model gpt-5-codex --timeout 600
```

`--agent auto` is the default and selects the first available supported agent CLI, preferring `claude` before `codex`. `--model` defaults to `sonnet`; pass an explicit model when using `codex`.

`hook-propose` groups findings by exact `prompt`. The number of records in each group becomes the `occurrences` count, which is evidence that a finding is recurring. File paths and reasons are deduplicated in first-seen order and capped before being shown to the agent, so very large logs stay prompt-sized while still preserving representative evidence.

The proposal prompt uses an evidence-sufficiency rubric:

- propose only when occurrences show a recurring, generalizable pattern;
- a single occurrence is weak evidence and should be proposed only if the reasons make the pattern unambiguous;
- otherwise, report it in `unmapped` with an insufficient-evidence reason;
- base every proposal only on the shown prompts, files, and reasons.

Exit codes:

| Exit | Meaning |
| --- | --- |
| `0` | Successful proposal, or no valid fail findings to promote. |
| `1` | Read/prompt/agent/JSON/schema/write failure. |

On failure, `hook-propose` does not write the proposal pack. If no findings exist, it prints a calm message and does not invoke an agent.

## Review workflow

`hook-propose` output is a proposal, not a config change. Review it the same way you review [`extract-rules`](./extracting-rules.md) output:

1. Open the generated pack.
2. Check that every convention is meaningful for your repository.
3. Delete, rename, narrow, or rewrite weak proposals.
4. Inspect the unmapped report.
5. Only after review, manually add the pack to `conventionSources`.

Example:

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

`hook-propose` never edits `konpy.json`.

## Suppressions

The promotion prompt explicitly refuses to propose or reference `# konpy: ignore[...]` suppression comments. Suppressions require explicit human approval and are out of scope for the ratchet. If a proposed convention would need an exception, review it manually under the [suppression consent policy](../reference/suppressions.md).

## See also

- [Agentic verification hooks](./hooks.md)
- [Claude Code hook integration](./claude-code-hook.md)
- [Extracting rules from prose](./extracting-rules.md)
- [Inferring conventions from an existing codebase](./inferring-conventions.md)
- [CLI reference](../reference/cli.md)
