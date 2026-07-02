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

`diagnostics` contains unsuppressed diagnostics only. `suppressed` contains diagnostics suppressed by source comments. `severity` is `"error"` or `"warning"`. `line` is omitted when the diagnostic isn't tied to a specific line (e.g., a missing-file diagnostic).

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

## Truncation

When the number of unsuppressed diagnostics exceeds `--max-diagnostics`, only the first `n` unsuppressed diagnostics are printed and a truncation summary is appended:

```text
... and 437 more diagnostics (use --max-diagnostics to see more)
```

The exit code still reflects all unsuppressed violations — only the printed output is truncated. Suppressed counts are computed from the full run result and are not truncated.
