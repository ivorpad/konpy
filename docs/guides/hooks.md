# Agentic verification hooks

`konpy hook` runs a read-only verifier after a coding agent writes or edits a file.

It supports two modes:

- one instruction supplied with `--prompt`;
- a package of named semantic rules supplied with `--rules`.

`konpy gate` remains the deterministic `PreToolUse` counterpart. `konpy check`, `konpy validate`, and `konpy gate` do not invoke an agent.

## Which hook mechanism should I use?

| | `konpy check --files` | `konpy gate` | `konpy hook` |
| --- | --- | --- | --- |
| Event | `PostToolUse` | `PreToolUse` | `PostToolUse` |
| Checks | Structural `konpy.json` conventions | Structural proposed content | Judgment-based single-file rules |
| Agent call | no | no | yes |
| Use when | Feedback after writing is enough | A deterministic rule must block before writing | A structural predicate cannot express the check |

These mechanisms can run side by side.

## Prompt mode

Use `--prompt` for one instruction:

```bash
konpy hook \
  --agent claude \
  --match 'src/**/*.py' \
  --prompt 'Verify that each function body does what its docstring claims.'
```

The verifier returns:

```json
{
  "verdict": "pass",
  "reasons": []
}
```

or:

```json
{
  "verdict": "fail",
  "reasons": [
    "The create_user docstring claims persistence, but the body only validates input."
  ]
}
```

This mode preserves the original `konpy hook` behavior.

## Rules mode

Use `--rules` for several named checks:

```bash
konpy hook \
  --agent claude \
  --match 'src/**/*.py' \
  --rules packs/team-style.rules.json
```

The package is documented in [Semantic rules](../reference/semantic-rules.md).

For each matched file, konpy selects rules whose own `match` globs match the path. It sends all applicable rules in one verifier request.

A file matching eight rules produces one agent call, not eight.

The rules verdict is:

```json
{
  "verdict": "fail",
  "failures": [
    {
      "rule": "contextual-errors",
      "reasons": [
        "The ValueError does not identify which account operation failed."
      ]
    },
    {
      "rule": "honest-docstrings",
      "reasons": [
        "The docstring claims persistence, but this function only validates."
      ]
    }
  ]
}
```

Feedback is written to stderr:

```text
contextual-errors: The ValueError does not identify which account operation failed.
honest-docstrings: The docstring claims persistence, but this function only validates.
```

## Mode and configuration errors

Exactly one of `--prompt` and `--rules` is required.

These fail open with exit `1`:

- neither mode supplied;
- both modes supplied;
- missing or invalid `--agent`;
- unreadable or invalid rules file;
- unrecognized hook arguments.

Mode validation happens inside `konpy hook`, not in Click's required-option handling. Exit `2` remains reserved for verified failures.

The recursion sentinel is checked first. A nested hook with `KONPY_HOOK_ACTIVE=1` exits `0` even if no mode is configured.

## Matching and batching

Filtering happens in this order:

1. Accept only a supported write tool.
2. Extract target paths.
3. Apply repeatable `--match` globs.
4. In rules mode, apply each rule's `match` globs.
5. Drop files with no applicable rules.

An empty `--match` list matches nothing.

Rules mode deduplicates target paths in first-seen order. A payload that names the same file twice still produces one verifier call for that file.

Files are checked sequentially. The hook stops after the first failed file or infrastructure error.

If no semantic rule applies, the hook returns `0` before resolving the agent executable.

## Exit-code contract

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | Pass or skip | Silent |
| `1` | Configuration or infrastructure failure | Error on stderr |
| `2` | Verified failure | Feedback on stderr |

A fail verdict with no rule failures still exits `2`. konpy assigns a synthesized reason to the first applicable rule:

```text
contextual-errors: Verification failed for src/service.py without a rule-specific reason.
```

A named rule failure without reasons receives the same fallback.

Unknown or inapplicable rule names make the verifier response invalid and exit `1`.

## Recursion guards

The child verifier receives `KONPY_HOOK_ACTIVE=1`. If a nested `konpy hook` sees that variable, it exits `0`.

The verifier is read-only:

- Claude receives `--allowedTools Read Grep Glob` and inline settings with hooks disabled.
- Codex receives `--sandbox read-only`.

The child cannot write a file and trigger another write hook.

## Timeouts

The default verifier timeout is 300 seconds:

```bash
konpy hook --timeout 120 ...
```

Keep the host hook timeout above the konpy timeout. A verifier timeout exits `1`.

## Claude Code setup

### Prompt mode

Add a `PostToolUse` command to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "konpy hook --agent claude --model sonnet --match 'src/**/*.py' --prompt 'Verify that docstrings match implemented behavior.'"
          }
        ]
      }
    ]
  }
}
```

### Rules mode

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "konpy hook --agent claude --model sonnet --match '**/*.py' --rules packs/team-style.rules.json --log .konpy/hook-findings.jsonl"
          }
        ]
      }
    ]
  }
}
```

Claude Code's matcher filters tool names. `konpy hook --match` filters file paths.

## Codex setup

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "apply_patch",
        "command": "konpy hook --agent codex --model gpt-5-codex --match '**/*.py' --rules packs/team-style.rules.json"
      }
    ]
  }
}
```

Codex reports writes as `apply_patch`. konpy extracts paths from the patch envelope or unified diff.

Set a Codex model explicitly because the default model name, `sonnet`, is intended for Claude.

## Persisting findings

Add `--log`:

```bash
konpy hook \
  --agent claude \
  --match '**/*.py' \
  --rules packs/team-style.rules.json \
  --log .konpy/hook-findings.jsonl
```

Prompt mode writes one finding for the first failed path.

Rules mode writes one finding per failed rule. Each record stores:

- the failed rule name in `rule`;
- the individual rule prompt in `prompt`;
- the reasons for that rule;
- file, session, tool, agent, model, and timestamp metadata.

Logging failures do not change exit `2`. Every failed rule append is attempted, then warnings are printed after verifier feedback.

Run `konpy hook-propose` to promote recurring findings. See [The ratchet](./ratchet.md).

## Rolling this out

Start with a narrow `--match`. Review latency and false positives before adding more paths or rules.

For deterministic checks, prefer `konpy.json`, `konpy check`, or `konpy gate`. Reserve semantic rules for checks that need judgment from one file.

## Suppressions

Hook feedback asks the coding agent to fix code. It does not authorize a `# konpy: ignore[...]` comment.

The [suppression consent policy](../reference/suppressions.md#ai-agents) still requires explicit human approval.

## See also

- [Semantic rules](../reference/semantic-rules.md)
- [Claude Code hook integration](./claude-code-hook.md)
- [Extracting rules from prose](./extracting-rules.md)
- [The ratchet](./ratchet.md)
