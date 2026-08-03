# Agentic verification hooks

`konpy review` runs a read-only verifier after a coding agent writes or edits a file and reports what it finds. It never blocks a write: exit `2` is not part of its contract. `konpy hook` is the older, deprecated sibling — same verifier, same modes, but it turns a fail verdict into exit `2` and blocks. `hook` is kept for compatibility; new setups should use `review`.

Both support two modes:

- one instruction supplied with `--prompt`;
- a package of named semantic rules supplied with `--rules`.

`konpy gate` is the deterministic `PreToolUse` counterpart — it blocks, but never calls a model. `konpy check`, `konpy validate`, and `konpy gate` never invoke an agent.

**The boundary:** semantic review can produce findings. Only a committed deterministic policy or test can produce a verification failure. A `review` finding is a model's opinion about one file — read it, act on it, and if it keeps recurring, promote it into a real rule (see [The ratchet](./ratchet.md)). It is never grounds to fail a write on its own.

## Which hook mechanism should I use?

| | Event | Checks | Agent call | Can block a write |
| --- | --- | --- | --- | --- |
| `konpy gate` | `PreToolUse` | Structural proposed content | no | yes, deterministically |
| `konpy review` | `PostToolUse` | Judgment-based single-file rules | yes | no, advisory only |
| `konpy hook` (deprecated) | `PostToolUse` | Judgment-based single-file rules | yes | yes, on a model verdict |

For structural `konpy.json` conventions after a write, with no model call, use `konpy check --files` — see [Claude Code hook integration](./claude-code-hook.md). These mechanisms can run side by side.

`konpy gate` fails open by default: a payload it can't parse or reconstruct lets the write through. Add `--fail-closed` to block those cases instead, for a hard-gate repo where a passing `PreToolUse` hook must mean the gate actually ran. See [`--fail-closed`](../reference/cli.md#--fail-closed) and [the PreToolUse recipe](./claude-code-hook.md#a-pretooluse-gate-with-konpy-gate). Either way, invoke `konpy gate` through a script your repository owns rather than inline in `.claude/settings.json`, so the hook and CI can't drift onto different flags.

## Prompt mode

Use `--prompt` for one instruction:

```bash
konpy review \
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

A fail verdict here is a finding, not a failure: `review` writes the reasons to stderr, adds them to the `additionalContext` JSON on stdout, and exits `0`.

## Rules mode

Use `--rules` for several named checks:

```bash
konpy review \
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

`review` keeps going after this file either way — one file's findings don't stop the rest of a multi-file batch from being checked, unlike `hook`.

## Mode and configuration errors

Exactly one of `--prompt` and `--rules` is required.

These exit `1`:

- neither mode supplied;
- both modes supplied;
- missing or invalid `--agent`;
- unreadable or invalid rules file;
- unrecognized arguments.

Mode validation happens inside `konpy review`, not in Click's required-option handling. Exit `1` is reserved for these local misconfigurations — a model verdict, however it comes out, always exits `0`.

The recursion sentinel is checked first. A nested run with `KONPY_HOOK_ACTIVE=1` exits `0` even if no mode is configured.

## Matching and batching

Filtering happens in this order:

1. Accept only a supported write tool.
2. Extract target paths.
3. Apply repeatable `--match` globs.
4. In rules mode, apply each rule's `match` globs.
5. Drop files with no applicable rules.

An empty `--match` list matches nothing.

Rules mode deduplicates target paths in first-seen order. A payload that names the same file twice still produces one verifier call for that file.

Files are checked sequentially. `review` checks every matched file regardless of what earlier files found; an agent-run failure or invalid verdict on one file is recorded as a warning and doesn't stop the rest.

If no semantic rule applies, `review` exits `0` before resolving the agent executable.

## Exit codes and output

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | Pass, skip, a review finding, or agent/infra trouble | Pass/skip: silent. A finding: reasons on stderr, one `additionalContext` JSON object on stdout. Agent/infra trouble: an error line on stderr (a missing agent binary is prefixed `konpy review: warning:`) |
| `1` | Local misconfiguration only — bad `--prompt`/`--rules`/`--agent` combination, or an unreadable/invalid rules file | Error on stderr |

`review` never exits `2`. A fail verdict with no rule failures still gets a synthesized reason for the first applicable rule:

```text
contextual-errors: Verification failed for src/service.py without a rule-specific reason.
```

A named rule failure without reasons receives the same fallback. Unknown or inapplicable rule names make the verifier response invalid, which is agent/infra trouble, not a finding — still exit `0`.

### `additionalContext`

When at least one finding was produced, stdout carries one JSON object:

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "konpy review findings:\nsrc/service.py: contextual-errors: The ValueError does not identify which account operation failed."}}
```

Claude Code folds `additionalContext` into the agent's next turn. Nothing is written to stdout for a clean pass.

## Recursion guards

The child verifier receives `KONPY_HOOK_ACTIVE=1`. If a nested `konpy review` (or `konpy hook`) sees that variable, it exits `0`.

The verifier is read-only:

- Claude receives `--allowedTools Read Grep Glob` and inline settings with hooks disabled.
- Codex receives `--sandbox read-only`.

The child cannot write a file and trigger another write hook.

## Timeouts

The default verifier timeout is 300 seconds:

```bash
konpy review --timeout 120 ...
```

Keep the host hook timeout above the konpy timeout. A verifier timeout writes an error line to stderr and, for `review`, never changes the exit code — it's agent/infra trouble, same as any other unavailable model. For the deprecated `hook`, a timeout is a `1`-exit infrastructure failure that stops the run.

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
            "command": "konpy review --agent claude --model sonnet --match 'src/**/*.py' --prompt 'Verify that docstrings match implemented behavior.'"
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
            "command": "konpy review --agent claude --model sonnet --match '**/*.py' --rules packs/team-style.rules.json --log .konpy/hook-findings.jsonl"
          }
        ]
      }
    ]
  }
}
```

Claude Code's matcher filters tool names. `konpy review --match` filters file paths.

## Codex setup

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "apply_patch",
        "command": "konpy review --agent codex --model gpt-5-codex --match '**/*.py' --rules packs/team-style.rules.json"
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
konpy review \
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

Logging failures don't change the exit code either way. Every failed rule append is attempted, then warnings are printed after verifier feedback.

Run `konpy hook-propose` to promote recurring findings. See [The ratchet](./ratchet.md).

## Rolling this out

Start with a narrow `--match`. Review latency and false positives before adding more paths or rules.

For deterministic checks, prefer `konpy.json`, `konpy check`, or `konpy gate`. Reserve semantic rules for checks that need judgment from one file — and remember a `review` finding is feedback, not a gate. If a check needs to actually block a write, it needs to be deterministic.

## Suppressions

Review feedback asks the coding agent to fix code. It does not authorize a `# konpy: ignore[...]` comment.

The [suppression consent policy](../reference/suppressions.md#ai-agents) still requires explicit human approval.

## Legacy: `konpy hook`

`konpy hook` predates `konpy review` and is deprecated. It exists for setups already depending on the blocking exit-code contract; prefer `review` for anything new.

Everything above — modes, matching, batching, recursion guards, `--log`, timeouts — works identically with `hook` in place of `review`, except:

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | Pass, or skip | Silent |
| `1` | Configuration or infrastructure failure | Error on stderr |
| `2` | A fail verdict | Feedback on stderr |

`hook` stops at the first failed file or infrastructure error instead of checking the rest of the batch, and it never writes `additionalContext` to stdout:

```bash
konpy hook \
  --agent claude \
  --match 'src/**/*.py' \
  --prompt 'Verify that each function body does what its docstring claims.'
```

To migrate a `.claude/settings.json` or `.codex/hooks.json` entry, replace `konpy hook` with `konpy review` on the command line. Nothing else needs to change.

## See also

- [Semantic rules](../reference/semantic-rules.md)
- [Claude Code hook integration](./claude-code-hook.md)
- [Extracting rules from prose](./extracting-rules.md)
- [The ratchet](./ratchet.md)
