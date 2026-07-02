# Agentic verification hooks

`konsistent hook` wires an agentic verifier into a coding agent's lifecycle hooks (Claude Code `PostToolUse`, Codex `PostToolUse`). After the host agent writes or edits a file, `konsistent hook` filters the event deterministically (tool name + `--match` glob), then spawns a verifier agent (`claude -p` or `codex exec`) with a natural-language prompt. A fail verdict is reported back to the host agent as blocking feedback so it can self-correct on its next turn.

`konsistent check` and `konsistent validate` never invoke an agent. `konsistent hook` is the only subcommand that does, and only when a matching write event actually occurs.

## Which hook mechanism should I use?

konsistent ships **two** distinct, unrelated PostToolUse hook mechanisms — pick the one that matches what you're verifying:

| | [`konsistent check --files` recipe](claude-code-hook.md) | `konsistent hook` (this guide) |
|---|---|---|
| Verifies | structural conventions in `konsistent.json` | anything expressible as a natural-language instruction |
| How | runs the deterministic linter directly | spawns a read-only LLM agent (`claude -p` / `codex exec`) per matched file |
| Cost | cheap — no LLM call, milliseconds | an agent invocation per matched write, seconds to tens of seconds |
| Setup | a shell script calling `konsistent check --files <path> --format json` | `konsistent hook --agent <claude|codex> --match <glob> --prompt <instruction>` directly as the hook command |
| Use when | you already have (or can write) a `konsistent.json` rule for it | the check is semantic/judgment-based and hard to express as a structural predicate (e.g. "docstrings aren't aspirational", "this class actually implements what its name claims") |

They can be run side by side — the deterministic recipe as a fast first pass, the agentic hook for the subset of checks that need judgment. Neither depends on the other.

## What it does

1. Reads a hook payload as JSON from stdin (the shape Claude Code and Codex both send to hook commands).
2. Skips silently (exit 0) unless the payload is a write-shaped tool call (`Write`/`Edit`/`MultiEdit` for Claude, `apply_patch` for Codex) on a path matching `--match`.
3. Builds a verification prompt from `--prompt` plus the matched file path and spawns the chosen `--agent` read-only, asking it to return one JSON verdict object.
4. Turns that verdict into a hook-protocol exit code.

## Exit-code contract

| Exit | Meaning | Output |
|---|---|---|
| 0 | pass, or skipped — sentinel env set, non-write tool, no extractable path, no `--match` hit, blank/unparseable payload | silent |
| 2 | verdict is **fail** — reserved exclusively for this | reasons written to stderr (the host feeds this back to the model) |
| 1 | infra fail-open — agent binary not on `PATH`, subprocess timeout or nonzero exit, unparseable agent output, bad `--agent` value | one line on stderr, non-blocking |

Exit 2 is never used for infra trouble, and exit 1 is never used for an actual fail verdict. A hook that can't run cleanly degrades to "no verification happened" rather than blocking the host agent.

`--prompt` and `--agent` are required, but that requirement is enforced by `konsistent hook` itself (exit 1), not by the CLI's own argument parser. A missing `--prompt`, a missing `--agent`, or an unrecognized `--agent` value (e.g. a stale `auto` copied from `extract-rules`, which doesn't accept it here) all fail open with exit 1 and a one-line stderr notice — never a CLI usage error, and never exit 2. This matters because the host feeds exit-2 stderr back to the coding model as blocking self-correction feedback; a hook misconfiguration must never be mistaken for that.

## Recursion guards

A `claude -p` or `codex exec` spawned from inside a hook would, by default, inherit the very same hooks — including this one. Two independent guards prevent runaway recursion:

- **Sentinel env var.** `konsistent hook` sets `KONSISTENT_HOOK_ACTIVE=1` in the child agent's environment before spawning it. If `konsistent hook` ever sees that variable already set (because it's running inside a nested agent invocation), it exits 0 immediately without doing any work.
- **Read-only child.** The verifier agent is also invoked with flags that keep it from writing anything: `claude` gets `--allowedTools Read Grep Glob` plus `--settings '{"hooks":{}}'` (inline JSON, no temp file — unlisted tools are auto-denied in `-p` mode); `codex` gets `--sandbox read-only`. A child that can't write can't re-trigger a `PostToolUse` write hook in the first place, sentinel or not.

Together these mean the verifier can read the file it's checking but cannot cause another round of hook firing.

## Timeouts: 300s default vs 600s host budget

`konsistent hook` spawns the verifier with a default timeout of 300 seconds (`--timeout`). Claude Code's and Codex's own hook command timeout defaults to 600 seconds. The 300s default leaves headroom under the host's 600s budget so a slow verifier run times out inside `konsistent hook` (producing a clean exit 1) rather than being killed by the host mid-flight. Raise `--timeout` only if you also confirm the host's own hook timeout is set high enough to accommodate it.

## Claude Code setup

Add a `PostToolUse` hook in `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "konsistent hook --agent claude --match 'src/**/*.py' --prompt 'Check that this module defines what it claims to: class and function names match their bodies, docstrings are not aspirational.'"
          }
        ]
      }
    ]
  }
}
```

Claude Code matchers match on **tool name only**, never on file path — `konsistent hook` does the path filtering itself via `--match`. `--match` is repeatable if you need more than one glob.

## Codex setup

Add a `PostToolUse` hook in `.codex/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "apply_patch",
        "command": "konsistent hook --agent codex --match 'src/**/*.py' --prompt 'Check that this module defines what it claims to: class and function names match their bodies, docstrings are not aspirational.'"
      }
    ]
  }
}
```

Codex reports its write tool as `apply_patch` regardless of whether the change looks like an add, update, or delete; `konsistent hook` recovers the touched path from the `apply_patch` envelope or a unified diff. If the payload shape can't be recognized, the hook skips (exit 0) rather than guessing.

## Rolling this out

Both snippets above are opt-in — adding them yourself. `konsistent` does not ship or install a live `.claude/settings.json` or `.codex/hooks.json`; wiring a verifier into your own agent session's hooks means it will fire during that session, so start with a narrow `--match` and a cheap prompt before widening scope.

## Suppressions

A fail verdict's `reasons` are self-correction feedback for the host agent, same as any other linter/test failure surfaced through a hook — they describe what's wrong so the agent can fix the code. Nothing about `konsistent hook`'s prompt or exit-code contract instructs an agent to reach for a `# konsistent: ignore[...]` suppression comment, and it never involves `konsistent check` at all. If a verifier's feedback ever seems to call for a suppression rather than a fix, the [suppression consent policy](../reference/suppressions.md#ai-agents) still applies in full: agents must not add one without explicit human approval.

## See also

[Claude Code hook integration](claude-code-hook.md) — the other, deterministic `konsistent check --files` `PostToolUse` recipe: no LLM call, verifies `konsistent.json` structural conventions only. Use that one first; reach for `konsistent hook` only for checks a structural predicate can't express.
