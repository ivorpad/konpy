# Claude Code hook integration

Run `konsistent check --files <edited-file>` automatically every time Claude Code edits or writes a Python file, using a Claude Code `PostToolUse` hook. This gives fast, scoped feedback without waiting for a full `konsistent check` run, and without requiring Claude to remember to run it. "Scoped" means *which conventions get selected*, not a promise that only the edited file gets checked — see the note on convention-level selection below.

This is the **deterministic** hook: it runs the linter directly, no LLM call. If you need to verify something a `konsistent.json` structural predicate can't express — a semantic/judgment check like "docstrings aren't aspirational" — see the separate, **agentic** [`konsistent hook`](hooks.md) subcommand instead, which spawns a read-only verifier agent per matched write. The two are independent and can be used together.

For flags and scoping semantics, see [Diff-scoped checking](../reference/cli.md#diff-scoped-checking---files----changed) in the CLI reference.

## Why `PostToolUse`, not `PreToolUse`

`PostToolUse` fires after the tool call already happened, so it can't block the edit — but that's fine here: we want to *react* to a completed edit, not prevent it. Per the Claude Code hooks model, `PostToolUse` cannot block; on exit code `2` its `stderr` is shown to Claude as feedback so it can fix the violation in a follow-up turn, which is exactly the workflow we want. On exit code `0`, hook stdout is not shown to Claude (only in the debug log) — so a clean check is silent, and only violations surface.

## 1. The hook script

Create `.claude/hooks/konsistent-check.sh`:

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

if ! output="$(uv run konsistent check --files "$file_path" --format json 2>&1)"; then
  echo "$output" >&2
  exit 2
fi

exit 0
```

`chmod +x .claude/hooks/konsistent-check.sh`. Requires [`jq`](https://jqlang.org/) on `PATH`.

Notes:

- `tool_input.file_path` may be an absolute or a project-relative path depending on how Claude invoked the tool; `konsistent check --files` accepts either (absolute paths outside the project directory simply match nothing and the check exits `0`).
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
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/konsistent-check.sh",
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
- `"timeout": 60` — seconds before the hook is killed; `konsistent check --files` on a single file should be well under this.

Place this file at `.claude/settings.json` to share it with your team (checked into git), or `.claude/settings.local.json` to keep it personal (gitignored). Project settings load automatically; no restart is required — hook configuration reloads live.

## 3. What Claude sees

- **Clean file**: hook exits `0`, nothing shown to Claude, the turn continues normally.
- **Violations found**: hook exits `2`; Claude's next context includes the `konsistent check --format json` output (from `stderr`) as tool feedback, e.g.:

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

  JSON is deliberately structured, not prose — `conventionName` and `predicateName` give Claude the stable identifiers it needs to locate the rule in `konsistent.json`, and `message`/`hint`/`fixHint` (when present) name the fix. Claude can then fix the violation in the same session, the same way it reacts to a failing test or lint error surfaced by any other hook.

## 4. Limitations to know about

- `PostToolUse` cannot prevent the edit — by the time the hook runs, the file is already on disk. This is a *feedback* loop, not a *gate*. For a hard gate, use a `PreToolUse` hook that runs `konsistent check --files <path>` against the *proposed* content before the edit is applied (more involved — requires diffing `tool_input` against the file to construct a temporary scratch copy — not covered by this guide) or rely on CI.
- Because `--files` selects whole conventions rather than individual files, a single edit can surface violations on files Claude didn't touch in this turn (any file sharing a selected convention's matched set, or any `unusedCode` finding project-wide). This is intentional — it is real, actionable signal, not noise — but it does mean hook output is not strictly bounded to the edited file. See [Diff-scoped checking](../reference/cli.md#diff-scoped-checking---files----changed) in the CLI reference for exactly which cases are and aren't covered.
