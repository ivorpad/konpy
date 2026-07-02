# CLI

The `konsistent` CLI is the entry point for running checks, validating configs, and explicitly generating reviewable reusable-convention proposals from prose rule sources.

Install it with `uv` or `pip`:

```bash
uv add --dev konsistent      # add to a uv project
uv run konsistent            # run it
uvx konsistent               # run without installing
pip install konsistent       # or install with pip
```

## Commands

| Command | Description |
| --- | --- |
| `konsistent` | Shorthand for `konsistent check` |
| `konsistent check` | Check structural conventions against your `konsistent.json` |
| `konsistent validate` | Validate the `konsistent.json` configuration file |
| `konsistent extract-rules` | Explicitly ask a local agent CLI to draft a reusable convention pack from prose rules |
| `konsistent explain` | Render the resolved config as prevention-side guidance markdown/text for a code-writing agent |
| `konsistent help` | Show a quick reference of all commands and options |
| `konsistent version` | Print the version number |

`konsistent` invoked without a subcommand runs `check`. `konsistent --help` runs `help`. `konsistent --version` prints the version. There is no `update` command.

Rule extraction is never implicit: `konsistent` only shells out to an agent when you run `konsistent extract-rules` directly.

## `check`

Loads `konsistent.json`, runs every convention against the codebase, and reports violations.

```bash
konsistent check
konsistent check --format=json --max-diagnostics=1000
konsistent check --error-on-warnings --diagnostic-level error
konsistent check --show-suppressed
```

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--config-path <path>` | string | `konsistent.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but **always errors as unsupported** in the Python port. Use `--config-path` instead |
| `--format <format>` | `default` \| `json` \| `github` \| `markdown` | `default` (auto-selects `github` in GitHub Actions) | Output format |
| `--verbose` | boolean | `false` | Accepted for upstream compatibility; produces no distinct output |
| `--max-diagnostics <n>` | integer | `100` | Maximum unsuppressed diagnostics to print before truncating |
| `--colors` / `--no-colors` | boolean | auto | Force-enable or disable terminal colors (default format only) |
| `--error-on-warnings` | boolean | `false` | Treat warnings as errors for the exit code |
| `--diagnostic-level <level>` | `warning` \| `error` | `warning` | Minimum severity to evaluate. `error` skips warning-severity conventions and suppression hygiene warnings |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, overriding any entry already there. May be passed multiple times. See [Static placeholder values](./path-patterns.md#static-placeholder-values) |
| `--show-suppressed` | boolean | `false` | List diagnostics suppressed by source comments in human-readable output |

`--config-package` is still unsupported. Installed Python distribution names are supported inside a local `konsistent.json` for `conventionSources` and `extends`; they do not enable loading the root config itself from a package.

Source-comment suppressions are documented in [Suppressions](./suppressions.md). Suppressed findings are still counted in summaries and included in JSON output.

### Exit codes

- `0` — no unsuppressed errors (warnings allowed unless `--error-on-warnings` is set).
- `1` — a config error, any unsuppressed error-severity diagnostic, or unsuppressed warnings when `--error-on-warnings` is set.

Suppressed errors do not fail the command. Suppressed warnings do not fail `--error-on-warnings`. Suppression hygiene diagnostics, such as unused suppressions, are normal warnings and do fail when `--error-on-warnings` is set.

## `validate`

Parses and validates `konsistent.json` against the schema without running any checks against the filesystem.

```bash
konsistent validate
konsistent validate --config-path=path/to/konsistent.json
```

Exits `0` and prints `Configuration is valid.` on success. Exits `1` with a validation error on failure.

`validate` accepts the same `--config-path`, `--config-package` (unsupported), and `--placeholder` flags as `check`.

## `extract-rules`

Explicitly asks a local agent CLI to convert prose rules into a reviewable [`ReusableConventionsPackageV1`](./reusable-conventions.md) proposal.

```bash
konsistent extract-rules docs/team-style-guide.md
konsistent extract-rules docs/team-style-guide.md -o packs/team-style.json
konsistent extract-rules docs/team-style-guide.md --agent codex --report unmapped.md
```

The command reads:

- the source file you pass;
- the full built-in predicate vocabulary from `docs/reference/predicates.md`;
- the reusable-conventions package format requirements; and
- a mappability rubric requiring unmappable rules to be reported, not silently dropped.

It sends that prompt to the selected agent CLI and expects one JSON object:

```json
{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "unmapped": [
    {
      "rule": "Use ruff for formatting.",
      "reason": "Formatting is enforced by Ruff, not konsistent predicates."
    }
  ]
}
```

The returned `pack` is validated with the same strict reusable-conventions schema used for `conventionSources` before anything is written.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `-o, --output <path>` | string | `packs/<source-stem>.json` | Path for the generated reusable convention pack proposal |
| `--agent <agent>` | `auto` \| `claude` \| `codex` | `auto` | Agent CLI to invoke |
| `--report <path>` | string | — | Write the unmapped-rules report to a file instead of printing it to stdout |

When `-o` is omitted, the output path is created under the current working directory as:

```text
packs/<source-stem>.json
```

For example:

```bash
konsistent extract-rules rules.md
# writes ./packs/rules.json
```

### Agent selection

`--agent auto` is the default. It picks the first available supported binary on `PATH` in this order:

1. `claude`
2. `codex`

The command invocation forms are:

```bash
claude -p <prompt>
codex exec <prompt>
```

If neither binary is available, `extract-rules` exits with an explicit error naming both `claude` and `codex`.

If you pass `--agent claude` or `--agent codex`, only that binary is considered. If it is missing, the command exits with an error naming the requested binary.

### Output and review workflow

A successful run writes only the reusable convention pack proposal. It never edits or creates `konsistent.json`.

After generation:

1. inspect the generated pack;
2. inspect the unmapped rules;
3. adjust or delete any bad proposal rules;
4. only then manually add the pack to `conventionSources` if you want to use it.

The proposal is intentionally human-reviewed. Agent output may be incomplete, over-broad, or structurally valid but semantically wrong for your repository.

### Unmapped rules

Rules that cannot be represented with built-in predicates, placeholders, and reusable-convention fields should be listed under `unmapped`.

Without `--report`, unmapped rules are printed to stdout:

```text
Wrote reusable convention proposal to packs/team-style.json
Unmapped rules:
- Use ruff for formatting.: Formatting belongs to Ruff.
```

With `--report`, the detailed list is written to the report path and stdout only names the files written:

```text
Wrote reusable convention proposal to packs/team-style.json
Wrote unmapped-rules report to unmapped.md
```

### Failure behavior

`extract-rules` exits `1` and writes nothing when:

- the source file cannot be read;
- no supported agent binary is available;
- the selected agent exits non-zero;
- the agent response does not contain a valid JSON object;
- the JSON object does not contain `pack` and `unmapped`;
- `unmapped` is not a list of `{ "rule": string, "reason": string }` objects;
- `pack` fails `ReusableConventionsPackageV1` validation.

Invalid packs report pydantic validation issues in the same style as other config errors.

## `explain`

Loads `konsistent.json`, resolves it exactly like `check`/`validate` do (after `extends`/`disable`/`conventionSources`/`plugins`), and renders every configured convention plus the `unusedCode` settings as concise Markdown (default) or plain-text guidance — suitable for pasting into `CLAUDE.md` or an equivalent agent instructions file so a code-writing agent follows the rules *before* writing code, instead of only being caught by `konsistent check` afterwards.

`explain` never touches the filesystem being linted and performs no diagnostic evaluation: it does not glob files, parse Python source, or run any predicate. `--diagnostic-level`, `--max-diagnostics`, `--colors`, `--error-on-warnings`, and `--show-suppressed` do not apply to it and are not accepted. It always renders every configured convention regardless of severity.

```bash
konsistent explain
konsistent explain --format text
konsistent explain --config-path path/to/konsistent.json > CLAUDE.md
```

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--config-path <path>` | string | `konsistent.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but **always errors as unsupported** in the Python port. Use `--config-path` instead |
| `--format <md\|text>` | `md` \| `text` | `md` | Output format |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, overriding any entry already there. May be passed multiple times |

Output is written to stdout only; there is no `--fix`/`--emit-patch`/file-write flag. Redirect it (`konsistent explain > CLAUDE.md`) or copy/paste the relevant sections into your agent instructions file.

Template placeholders (`${name}`, `${name.method(...)}`) inside `paths` or predicate values are rendered **verbatim, unresolved** — there is no per-file match context at explain time, only the resolved config. This is a deliberate scope decision, not a bug.

Sample Markdown output:

```md
# Project conventions

Structural conventions enforced by `konsistent`. Follow these before writing or editing Python files in this repository.

## Conventions

- **`documented-service`** (severity: `error`) — paths: `src/service.py`
  - Service modules must be paired and documented.
  - hint: Create the paired test file next to the service module.
  - must: `havePairedFile` tests/test_{name}.py

## Suppressions

Suppression comments (`konsistent: ignore[rule]`) are for approved exceptions only. Never add one without explicit human approval -- see `docs/reference/suppressions.md`. Fix the violation, or ask a human to approve a suppression with a reason.
```

Each convention bullet shows its resolved name (generated the same way `check`'s suppression-comment matching would name it, when no explicit `name` is set), paths, `description`, `hint`, and `severity`, followed by its `must`/`mustNot` predicates. Conventions with multiple `must` blocks label each block by name (or `block N`) so conditional (`if`/`for`/`excludeFiles`) rules stay unambiguous. When `unusedCode` is configured, a `## Unused code` section lists the fully resolved include/exclude globs, entrypoint files, registry decorators, hook names, model base classes, and any explicit `allow` list — including framework presets, not just what you wrote in `konsistent.json`. Every render ends with a standing `## Suppressions` note reiterating the [suppression consent policy](./suppressions.md#ai-agents): agents must never add a `# konsistent: ignore[...]` comment without explicit human approval.

## Output formats

### `default`

Colored terminal output. Files are grouped, diagnostics sorted by line.

```text
packages/anthropic/src/__init__.py
  -  error  Missing export type "AnthropicProvider"  [must-export-and-more]

packages/openai/src/__init__.py
  -  error  Missing export "openai"  [must-export-and-more]
  -  error  Missing export type "OpenAIProviderSettings"  [must-export-and-more]

Checked 6 files in 10ms. Found 3 errors.
```

When a diagnostic carries a convention `description`/`hint` or a predicate-supplied `expected`/`found`/`fix_hint` (see [Diagnostic intent and fix direction](#diagnostic-intent-and-fix-direction) below), an extra line follows the diagnostic:

```text
src/service.py
  -  error  Missing paired file: tests/test_service.py  [documented-service]
        -> description: Service modules must be paired and documented. | expected: tests/test_service.py | fix: Create the paired file at "tests/test_service.py".
```

This line never appears for diagnostics that carry none of those fields, so existing output is unaffected.

When everything passes:

```text
Checked 6 files in 8ms. No violations found.
```

When findings are suppressed:

```text
Checked 3 files in 5ms. No unsuppressed violations found. Suppressed 2 findings.
Checked 3 files in 5ms. Found 1 error and 2 warnings. Suppressed 3 findings.
```

With `--show-suppressed`, default output includes suppressed details before the summary:

```text
Suppressed diagnostics:
src/service.py
  4  suppressed warning  Definition "legacy" is only referenced by tests  [unused-code]  (suppressed by line 3: legacy API)

Checked 1 file in 5ms. No unsuppressed violations found. Suppressed 1 finding.
```

### `github`

GitHub Actions annotations (`::error file=...,line=...::message` and `::warning ...`). Auto-selected when `GITHUB_ACTIONS=true` is set in the environment, so `konsistent check` in a GitHub workflow needs no extra flags.

By default, suppressed diagnostics are not emitted as GitHub annotations. With `--show-suppressed`, suppressed diagnostics are emitted as notices:

```text
::notice file=src/service.py,line=4,title=Suppressed unused-code::warning: Definition "legacy" is only referenced by tests (suppressed by line 3: legacy API)
```

### `json`

Machine-readable JSON object. It always includes unsuppressed diagnostics, suppressed diagnostics, and a summary:

```json
{
  "diagnostics": [
    {
      "severity": "error",
      "conventionName": "must-export-and-more",
      "filePath": "packages/openai/src/__init__.py",
      "predicateName": "export",
      "message": "Missing export \"openai\"",
      "line": 1
    },
    {
      "severity": "error",
      "conventionName": "documented-service",
      "filePath": "src/service.py",
      "predicateName": "havePairedFile",
      "message": "Missing paired file: tests/test_service.py",
      "description": "Service modules must be paired and documented.",
      "expected": "tests/test_service.py",
      "fixHint": "Create the paired file at \"tests/test_service.py\"."
    }
  ],
  "suppressed": [
    {
      "severity": "warning",
      "conventionName": "unused-code",
      "filePath": "src/service.py",
      "predicateName": "unusedCode.dead",
      "message": "Unused definition \"legacy\" is never referenced",
      "line": 4,
      "suppressedBy": {
        "kind": "ignore",
        "filePath": "src/service.py",
        "line": 3,
        "reason": "legacy API"
      }
    }
  ],
  "summary": {
    "filesChecked": 6,
    "errors": 1,
    "warnings": 0,
    "suppressed": 1,
    "durationMs": 10.0
  }
}
```

`diagnostics` contains unsuppressed diagnostics only. `suppressed` contains diagnostics suppressed by source comments. `severity` is `"error"` or `"warning"`. `line`, `description`, `hint`, `expected`, `found`, and `fixHint` are all omitted (never emitted as `null`) when not applicable to that diagnostic — see [Diagnostic intent and fix direction](#diagnostic-intent-and-fix-direction).

`--show-suppressed` does not change JSON output; suppressed details are always present so machine consumers can audit them.

Use `json` when scripting around the CLI (CI gating, custom reports, or driving an agent).

### `markdown`

Markdown table format suitable for posting as a PR comment.

Markdown summaries mirror the default format and include suppressed counts:

```md
**Checked 3 files in 5ms. No unsuppressed violations found. Suppressed 2 findings.**
```

With `--show-suppressed`, Markdown includes a suppressed diagnostics section:

```md
### Suppressed diagnostics

**`src/service.py`**

| Line | Severity | Message | Convention | Suppressed By | Reason |
|------|----------|---------|------------|---------------|--------|
| 4 | warning | Definition "legacy" is only referenced by tests | unused-code | line 3 | legacy API |
```

When a diagnostic carries `description`/`hint`/`expected`/`found`/`fix_hint`, the `Message` cell gets an additive `<br><sub>...</sub>` suffix (GitHub-flavored Markdown tables tolerate inline HTML; a literal newline would break the table):

```md
| Line | Severity | Message | Convention |
|------|----------|---------|------------|
| - | error | Missing paired file: tests/test_service.py<br><sub>expected: tests/test_service.py \| fix: Create the paired file at "tests/test_service.py".</sub> | documented-service |
```

`github` format is unaffected by this feature — GitHub annotations stay message-only.

## Diagnostic intent and fix direction

Beyond `message`, a diagnostic may carry up to five additional, always-optional fields that name the *intent* behind a rule and the *direction* of the fix, so an agent's next edit is unambiguous without re-deriving it from the message string:

| Field | Source | Meaning |
|-------|--------|---------|
| `description` | The convention's (or `must`-block's) `description` | Why this rule exists. Inherited automatically by every diagnostic the convention produces, regardless of which predicate raised it. |
| `hint` | The convention's (or `must`-block's) optional `hint` config field | An author-supplied nudge for fixing violations of this convention (see [Configuration](./configuration.md#hint)). |
| `expected` | The predicate | What the predicate wanted to find (a name, path, base class, regex pattern, ...). |
| `found` | The predicate | What the predicate found instead, when the failure is "wrong value" rather than "absent". Omitted (not `null`) when there is nothing meaningful to report as found. |
| `fix_hint` (`fixHint` in JSON) | The predicate | A concrete, actionable next step, phrased as an instruction. |

A block's own `description`/`hint` override the parent convention's when both are set (same precedence as `name`).

`expected`/`found`/`fix_hint` are populated by the predicates where they can be expressed unambiguously: `exportClasses`, `exportConstants`, `havePairedFile`, `haveDocstrings`, `annotateFunctions`, `importFrom`, `importFrom*`/`importTypes*` (current-dir/parents/externals groups), and `matchContent`. Other predicates leave these fields `None` rather than guessing — a vague hint is worse than no hint.

All five fields are additive and optional everywhere they appear: omitted from JSON when absent (never emitted as `null`), and producing no extra line/cell in `default`/`markdown` output when absent. `fix_hint` is data only — konsistent never applies it automatically and never emits suppression comments; see [Suppressions](./suppressions.md) for the consent policy on machine-authored changes.

## Truncation

When the number of unsuppressed diagnostics exceeds `--max-diagnostics`, only the first `n` unsuppressed diagnostics are printed and a truncation summary is appended:

```text
... and 437 more diagnostics (use --max-diagnostics to see more)
```

The exit code still reflects all unsuppressed violations — only the printed output is truncated. Suppressed counts are computed from the full run result and are not truncated.
