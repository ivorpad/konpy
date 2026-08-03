# Claude Code hook integration

Run `konpy check --files <edited-file>` automatically every time Claude Code edits or writes a Python file, using a Claude Code `PostToolUse` hook. This gives fast, scoped feedback without waiting for a full `konpy check` run, and without requiring Claude to remember to run it. "Scoped" means *which conventions get selected*, not a promise that only the edited file gets checked — see the note on convention-level selection below.

This is the **deterministic PostToolUse** hook: it runs the linter directly after a write, no LLM call. If you need to verify something a `konpy.json` structural predicate can't express — a semantic/judgment check like "docstrings aren't aspirational" — see the separate, **agentic** [`konpy review`](#an-advisory-posttooluse-review-with-konpy-review) flow below, which spawns a read-only verifier agent per matched write and reports findings without blocking. If you need to block non-conforming proposed content before it reaches disk, use the **deterministic PreToolUse** [`konpy gate`](#a-pretooluse-gate-with-konpy-gate) flow. All three mechanisms are independent and can be used together.

See also: [The ratchet](ratchet.md) shows how logged review findings can be promoted into deterministic conventions that this hook then enforces model-free.

For flags and scoping semantics, see [Diff-scoped checking](../reference/cli.md#diff-scoped-checking---files----changed) in the CLI reference.

## Why `PostToolUse`, not `PreToolUse`

`PostToolUse` fires after the tool call already happened, so it can't block the edit — but that's fine here: we want to *react* to a completed edit, not prevent it. Per the Claude Code hooks model, `PostToolUse` cannot block; on exit code `2` its `stderr` is shown to Claude as feedback so it can fix the violation in a follow-up turn, which is exactly the workflow we want. On exit code `0`, hook stdout is not shown to Claude (only in the debug log) — so a clean check is silent, and only violations surface.

If you do want a hard gate, use [`konpy gate`](#a-pretooluse-gate-with-konpy-gate): it is a `PreToolUse` command that reconstructs Claude Code's proposed `Write`/`Edit`/`MultiEdit` content in memory and runs the same deterministic checks before the write lands.

## 1. The hook script

Create `.claude/hooks/konpy-check.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Read the PostToolUse JSON payload from stdin and extract
# tool_input.file_path (present for Edit/Write tool calls).
file_path="$(jq -r '.tool_input.file_path // empty')"

# Only check Python files; silently no-op otherwise.
if [[ -z "$file_path" || "$file_path" != *.py ]]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

if ! output="$(uv run konpy check --files "$file_path" --format json 2>&1)"; then
  echo "$output" >&2
  exit 2
fi

exit 0
```

`chmod +x .claude/hooks/konpy-check.sh`. Requires [`jq`](https://jqlang.org/) on `PATH`.

Notes:

- `tool_input.file_path` may be an absolute or a project-relative path depending on how Claude invoked the tool; `konpy check --files` accepts either (absolute paths outside the project directory simply match nothing and the check exits `0`).
- This intentionally scopes to the single edited file (`--files`, not `--changed`) — fast, and targeted at exactly what Claude just touched. Selection is convention-level, though: any convention whose matched set includes the edited file is evaluated over its *entire* matched set, so a violation on a sibling file that shares that convention is still reported, not silently missed. Swap in `--changed` instead if you'd rather select every convention touched by every uncommitted change on every edit (slower, broader) — but note `--changed` **requires a git repository**: outside one it prints a single clear message to stderr and exits `1` rather than falling back to a full scan, so only use it in a hook you know runs inside a checked-out repo.
- `havePairedFile` fires correctly even when the hook only sees one side of a declared pair (e.g. Claude edits/deletes `tests/test_service.py` and never touches `src/service.py`): selection accounts for the predicate's resolved companion path, so the convention anchored at the other side is still selected and evaluated in full (see [Diff-scoped checking](../reference/cli.md#diff-scoped-checking---files----changed)). `unusedCode`, by contrast, always runs and reports in full regardless of scope, so it fires on every edit that has any `unusedCode` config at all — expect its output to include unrelated files, since it is never narrowed by `--files`/`--changed`.

## 2. Wire it up in `.claude/settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/konpy-check.sh",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

Field notes (from the Claude Code hooks schema):

- `"matcher": "Edit|Write"` — only fires for the `Edit` and `Write` tools (a `|`-separated exact-name list; use `"*"` or omit the field to match every tool instead).
- `"type": "command"` — runs a shell command; `"command"` is `${CLAUDE_PROJECT_DIR}`-relative so the hook works regardless of Claude's current working directory.
- `"timeout": 60` — seconds before the hook is killed; `konpy check --files` on a single file should be well under this.

Place this file at `.claude/settings.json` to share it with your team (checked into git), or `.claude/settings.local.json` to keep it personal (gitignored). Project settings load automatically; no restart is required — hook configuration reloads live.

## 3. What Claude sees

- **Clean file**: hook exits `0`, nothing shown to Claude, the turn continues normally.
- **Violations found**: hook exits `2`; Claude's next context includes the `konpy check --format json` output (from `stderr`) as tool feedback, e.g.:

  ```json
  {
    "diagnostics": [
      {
        "severity": "error",
        "conventionName": "service-must-export-process",
        "filePath": "src/service.py",
        "predicateName": "export",
        "message": "Missing export \"process\""
      }
    ],
    "suppressed": [],
    "summary": {
      "filesChecked": 1,
      "errors": 1,
      "warnings": 0,
      "suppressed": 0,
      "durationMs": 0.75
    }
  }
  ```

  JSON is deliberately structured, not prose — `conventionName` and `predicateName` give Claude the stable identifiers it needs to locate the rule in `konpy.json`, and `message`/`hint`/`fixHint` (when present) name the fix. Claude can then fix the violation in the same session, the same way it reacts to a failing test or lint error surfaced by any other hook.

## A PreToolUse gate with `konpy gate`

Use `konpy gate` when you want Claude Code to block a proposed write before it reaches disk. Unlike the shell recipe above, no `jq` wrapper is needed: `konpy gate` reads the `PreToolUse` payload from stdin, reconstructs the proposed content for Claude Code `Write`, `Edit`, and `MultiEdit` calls, checks that content in-process through an overlay filesystem, and exits `2` only for verified convention violations.

Add a `PreToolUse` hook in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run konpy gate --match 'src/**/*.py'",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

Field notes:

- `"matcher": "Edit|Write|MultiEdit"` keeps the hook on Claude Code write tools whose proposed content `konpy gate` can reconstruct.
- `--match` is a repeatable glob filter applied to the target path. If omitted, `konpy gate` gates every target path in the payload.
- On a block, `konpy gate` writes the same JSON object shape as `konpy check --format json` to `stderr`, then exits `2`, so Claude sees stable fields like `conventionName`, `predicateName`, `message`, `hint`, and `fixHint`.
- Clean proposed content exits `0` silently.
- Config/load/runtime failures fail open by default: the write proceeds, and `stderr` gets one `konpy gate: warning: <detail>` line.
- Unreconstructable payloads fail open by default. In v1, Codex-style `apply_patch` reconstruction is out of scope; the gate is Claude-Code-first for `Write`/`Edit`/`MultiEdit`.
- Add `--fail-closed` to block instead of allow when any of the above happens. See [`--fail-closed`](../reference/cli.md#--fail-closed) in the CLI reference for the exact list of cases and the stderr message shape.
- `unusedCode` (the whole-project dead-code scan) is skipped by default to keep the gate fast on every single-file write, and only runs when `--error-on-warnings` is set, since that's the only mode where its warning-severity findings could change the block/pass outcome.
- Add `--ruff` to also run `ruff check` against every proposed `.py` write, using the target repo's own ruff config; findings block like any other verified violation. See [`--ruff`](../reference/cli.md#--ruff) in the CLI reference.

Claude Code also supports a structured stdout JSON permission-decision channel for `PreToolUse` hooks, but `konpy gate` intentionally uses exit `2` plus stderr in v1 to match the same feedback shape as the deterministic `check --files` recipe above and the deprecated `konpy hook`. Only `gate` actually blocks, being `PreToolUse`; `check --files` and `hook` fire after the write already landed. `konpy review` shares the payload/agent plumbing with `hook` but never exit `2` — see the boundary below.

### Fail-open or fail-closed?

The default fail-open behavior is right for most repos: a config typo or a payload konpy can't reconstruct shouldn't block every write. Switch to `--fail-closed` for a hard-gate repo, where "the gate passed" must never quietly mean "the gate didn't run": CI or a human review is the fallback, not silent allow.

```json
{
  "type": "command",
  "command": "uv run konpy gate --match 'src/**/*.py' --fail-closed",
  "timeout": 60
}
```

Whichever mode you pick, wrap the `konpy gate` invocation in a script your repository already owns (e.g. `scripts/verify`) instead of inlining the full flag list in `.claude/settings.json`. CI and the hook then call the same entry point, so a flag change (adding `--fail-closed`, tightening `--match`, raising `--max-diagnostics`) can't drift between the two.

## An advisory PostToolUse review with `konpy review`

Use `konpy review` when you want a model to look at what Claude just wrote and report anything worth knowing, without deciding whether the write stands. Semantic review can produce findings; only a committed deterministic policy or test — `konpy check`/`konpy gate` against `konpy.json` — can produce a verification failure. Like `konpy gate`, no `jq` wrapper is needed: `review` reads the `PostToolUse` payload from stdin itself, spawns a read-only verifier agent per matched write, and exits `0` no matter what the model concludes.

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
            "command": "konpy review --agent claude --model sonnet --match 'src/**/*.py' --prompt 'Verify that docstrings match implemented behavior.'"
          }
        ]
      }
    ]
  }
}
```

Field notes:

- `--match` filters the target path the same way `konpy gate` does; an empty `--match` list matches nothing.
- `--prompt` is one instruction; use `--rules packs/team-style.rules.json` instead for several named checks in one agent call per file — see [Semantic rules](../reference/semantic-rules.md).
- On a finding, `review` writes reasons to stderr and one `additionalContext` JSON object to stdout, then exits `0`. Claude Code folds `additionalContext` into the agent's next turn.
- A missing or unreachable verifier agent degrades to a `konpy review: warning:` stderr line, still exit `0` — an unavailable model must not block a write.
- Add `--log .konpy/hook-findings.jsonl` to persist findings for [`konpy hook-propose`](../reference/cli.md#hook-propose) — see [The ratchet](ratchet.md).

Full command reference, exit codes, and the `additionalContext` shape: [`review`](../reference/cli.md#review) in the CLI reference, and [Agentic verification hooks](hooks.md) for prompt mode vs. rules mode, batching, and Codex setup.

### Legacy: `konpy hook`

`konpy hook` is the deprecated predecessor to `konpy review`: identical flags and payload handling, but a fail verdict exits `2` and blocks instead of reporting a finding. It's kept for repos already depending on that contract, not recommended for new ones. The recipe and full exit-code contract live at [Legacy: `konpy hook`](hooks.md#legacy-konpy-hook) in the agentic verification guide; migrating means replacing `konpy hook` with `konpy review` on the command line, nothing else.

## 4. Limitations to know about

- The shell `PostToolUse` recipe cannot prevent the edit — by the time the hook runs, the file is already on disk. This is a *feedback* loop, not a *gate*. For a hard gate, use the [`PreToolUse` `konpy gate`](#a-pretooluse-gate-with-konpy-gate) flow above or rely on CI.
- `konpy gate` reconstructs Claude Code `Write`, `Edit`, and `MultiEdit` payloads only. Codex `apply_patch` always fails open (out of scope in v1, not affected by `--fail-closed`). Malformed or unreconstructable `Write`/`Edit`/`MultiEdit` payloads fail open by default too, unless `--fail-closed` is set, in which case they block.
- Because `--files` selects whole conventions rather than individual files, a single edit can surface violations on files Claude didn't touch in this turn (any file sharing a selected convention's matched set, or any `unusedCode` finding project-wide). This is intentional — it is real, actionable signal, not noise — but it does mean hook output is not strictly bounded to the edited file. See [Diff-scoped checking](../reference/cli.md#diff-scoped-checking---files----changed) in the CLI reference for exactly which cases are and aren't covered.
