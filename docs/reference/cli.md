# CLI

The `konpy` CLI is the entry point for running checks, validating configs, and explicitly generating reviewable reusable-convention proposals from prose rule sources.

Install it with `uv` or `pip`:

```bash
uv add --dev konpy      # add to a uv project
uv run konpy            # zero-config report; `konpy check` runs the conventions
uvx konpy               # run without installing
pip install konpy       # or install with pip
```

## Commands

| Command | Description |
| --- | --- |
| `konpy` | Zero-config codebase report (same as `konpy report`) |
| `konpy report` | Unused code, duplication, and coverage over `**/*.py` — no config required |
| `konpy check` | Check structural conventions against your `konpy.json` |
| `konpy validate` | Validate the `konpy.json` configuration file |
| `konpy init` | Write a starter `konpy.json` into the current directory |
| `konpy docs` | Print bundled reference docs (`konpy docs [topic]`) |
| `konpy extract-rules` | Explicitly ask a local agent CLI to draft a reusable convention pack from prose rules |
| `konpy infer` | Mine the codebase for candidate structural conventions and emit a reviewable proposal |
| `konpy explain` | Render the resolved config as prevention-side guidance markdown/text for a code-writing agent |
| `konpy gate` | Run a deterministic Claude Code `PreToolUse` gate against proposed content |
| `konpy hook` | Run an agentic `PostToolUse` verification hook for Claude Code or Codex |
| `konpy help` | Show a quick reference of all commands and options |
| `konpy version` | Print the version number |

Bare `konpy` runs the zero-config report; options without a subcommand (e.g. `konpy --files a.py`) still imply `check`. `konpy help` prints the full help with a getting-started brief. `konpy --version` prints the version. There is no `update` command.

Rule extraction is never implicit: `konpy` only shells out to an agent when you run `konpy extract-rules` directly, or when a `konpy hook` invocation actually matches a write event. `konpy gate` runs deterministic checks in-process and never shells out to an agent.

## `check`

Loads `konpy.json`, runs every convention against the codebase, and reports violations.

```bash
konpy check
konpy check --format=json --max-diagnostics=1000
konpy check --error-on-warnings --diagnostic-level error
konpy check --show-suppressed
konpy check --files src/service.py
konpy check --changed
```

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--config-path <path>` | string | `konpy.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but **always errors as unsupported** in the Python port. Use `--config-path` instead |
| `--format <format>` | `default` \| `json` \| `github` \| `markdown` | `default` (auto-selects `github` in GitHub Actions) | Output format |
| `--verbose` | boolean | `false` | Accepted for upstream compatibility; produces no distinct output |
| `--max-diagnostics <n>` | integer | `100` | Maximum unsuppressed diagnostics to print before truncating |
| `--colors` / `--no-colors` | boolean | auto | Force-enable or disable terminal colors (default format only) |
| `--error-on-warnings` | boolean | `false` | Treat warnings as errors for the exit code |
| `--diagnostic-level <level>` | `warning` \| `error` | `warning` | Minimum severity to evaluate. `error` skips warning-severity conventions and suppression hygiene warnings |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, overriding any entry already there. May be passed multiple times. See [Static placeholder values](./path-patterns.md#static-placeholder-values) |
| `--show-suppressed` | boolean | `false` | List diagnostics suppressed by source comments in human-readable output |
| `--files <path> [<path> ...]` | string (repeatable or space list) | — | Restrict checking to these files. May be repeated (`--files a.py --files b.py`) or given as one space-separated occurrence (`--files a.py b.py`). Mutually exclusive with `--changed` |
| `--changed` | boolean | `false` | Restrict checking to files changed since `HEAD` (`git diff --name-only HEAD`) plus untracked files (`git ls-files --others --exclude-standard`). Mutually exclusive with `--files` |

`--config-package` is still unsupported. Installed Python distribution names are supported inside a local `konpy.json` for `conventionSources` and `extends`; they do not enable loading the root config itself from a package.

`--changed` shells out to `git` and **requires a git repository**: if the working directory is not inside one, `check` prints a single, deliberate message (`--changed requires a git repository (none found at <cwd>).`) to stderr and exits `1` — it never relays git's raw stderr/usage output for this case. If the underlying `git` invocation otherwise fails, `check` prints that git error to stderr and exits `1`. Neither case falls back to a full, unscoped scan. Only rely on `--changed` where a git repository is guaranteed, e.g. a CI job or a hook running inside a checked-out repo.

Source-comment suppressions are documented in [Suppressions](./suppressions.md). Suppressed findings are still counted in summaries and included in JSON output.

### Diff-scoped checking (`--files` / `--changed`)

`--files` and `--changed` restrict *which conventions get selected*, not which files a selected convention evaluates. Selection is convention-level: a convention is selected when **any** file in its `paths` matched set is in scope, and once selected it is evaluated over its **entire** matched set — never just the in-scope subset. A convention whose matched set has zero intersection with the requested scope is skipped entirely and produces no diagnostics for that run.

This matters because several predicates are cross-file: e.g. a `paths: "src/*.py"` convention where `src/a.py` and `src/b.py` both match is a single unit of evaluation. Scoping to `src/a.py` alone still selects that convention, and the run can still report a pre-existing violation on `src/b.py` — scoping never naively narrows a selected convention down to only the literally-passed files. Everything else (config validation, suppression hygiene checks, exit-code semantics) behaves the same as an unscoped run.

Path matching uses prefix intersection, not just exact equality: a directory-scoped convention (`paths` matching a directory) is selected when a file *inside* that directory is in scope, and vice versa.

Cross-file checks need extra selection context and are handled deliberately:

- **`havePairedFile`** always checks the *entire* filesystem for the companion file, so it stays fully correct for every file it evaluates under scoping. Selection also accounts for this predicate being cross-file: if *only* the companion side of a declared pair is in scope (e.g. only `tests/test_service.py` changed, not the `src/service.py` the convention's `paths` targets), the convention is still selected and evaluated over its full matched set — so a broken pairing produced by editing or deleting just the companion is still reported, not silently missed.
- **`restrictRepeatedLiterals`** and **`restrictDuplicateFunctions`** build their groups over the full effective file set of the convention or nested `for` block, after `excludeFiles` is applied. Under `--files`/`--changed`, selection accounts for that block scope: if any file in the block's effective scope is in scope, the convention is selected, and the predicate still evaluates the full block scope rather than only the requested file(s).
- **`unusedCode`** always scans the *entire* project to build its reference index (required for correct dead/test-only classification), and, unlike ordinary conventions, is never filtered by `--files`/`--changed` at all: every run reports its full, whole-project diagnostics regardless of scope. Filtering `unusedCode` output down to the requested scope would silently hide dead code living outside it, so scoping simply does not apply to it — `--files`/`--changed` do **not** speed up or narrow `unusedCode` checks.

Examples:

```bash
konpy check --files src/service.py
konpy check --files src/service.py src/other.py
konpy check --files src/service.py --files src/other.py
konpy check --changed
```

See also: the [Claude Code hook integration guide](../guides/claude-code-hook.md), which uses `--files` to check a single edited file after every `Edit`/`Write` tool call. Because selection is convention-level, this still gives full-fidelity feedback: if the edited file shares a convention with other files, violations on those other files are reported too, not silently missed.

### Exit codes

- `0` — no unsuppressed errors (warnings allowed unless `--error-on-warnings` is set).
- `1` — a config error, any unsuppressed error-severity diagnostic, or unsuppressed warnings when `--error-on-warnings` is set.

Suppressed errors do not fail the command. Suppressed warnings do not fail `--error-on-warnings`. Suppression hygiene diagnostics, such as unused suppressions, are normal warnings and do fail when `--error-on-warnings` is set.

## `validate`

Parses and validates `konpy.json` against the schema without running any checks against the filesystem.

```bash
konpy validate
konpy validate --config-path=path/to/konpy.json
```

Exits `0` and prints `Configuration is valid.` on success. Exits `1` with a validation error on failure.

`validate` accepts the same `--config-path`, `--config-package` (unsupported), and `--placeholder` flags as `check`.

## `report`

The zero-config analysis that bare `konpy` runs — no `konpy.json` required. Lanes, all at engine defaults over `**/*.py` (dot-directories like `.venv` are never traversed; `node_modules`, `venv`, `build`, `dist`, `__pycache__`, `*.egg-info`, and `site-packages` are excluded):

- **Conventions** — only when `konpy.json` exists: the standard check runs and its errors/warnings summarize into the report (an invalid config is reported without killing the other lanes).
- **Unused code** — the [unused-code engine](unused-code.md) at defaults; test files feed the reference index but never carry findings.
- **Duplication** — repeated string literals (≥8 chars, more than 2 occurrences) and duplicate function implementations (≥4 statements, alpha-renamed fingerprints), tests excluded.
- **Coverage** — docstring coverage for public modules/classes/functions and fully-annotated public function ratio; `konpy infer` turns these into enforceable ratchet proposals.

Generated code is detected per file by generator banners in the first lines (`@generated`, `auto-generated`, `DO NOT EDIT`, `# Generated by ...` comments — Fern/OpenAPI clients, protobuf stubs, Django migrations), minus any paths listed in a `.fernignore` (those are hand-maintained even when they carry a stale banner). Generated files are counted in the report header, feed the unused lane's reference index without carrying findings (so hand-written code called only from generated code stays used), are excluded from coverage stats, and duplicate groups confined to them are tagged `[generator template]` instead of being presented as copy-paste.

Duplicate groups whose members all live under example or documentation directories (`examples/`, `docs_src/`, `docs/`, `samples/`) are tagged `[example/docs code]`: tutorial snippets repeat setup code so each one stands alone. A duplicate spanning example and production code is not tagged — that one is real.

Two more duplication-lane refinements: repeated literals dominated by **mapping-key positions** (dict-display keys, subscript indexes, `.get()`/`.pop()`/`.setdefault()` arguments — ≥90% of occurrences) are tagged `[mapping keys]` and ranked after everything else, because serialization boundaries — OpenSearch mappings, IAM policies, API payloads — repeat keys by protocol necessity. And a duplicate-function group whose members carry different names lists them (`iter_error_chain a.k.a. iter_retry_error_chain`) so a rename can't hide a copy-paste.

```bash
konpy            # bare invocation
konpy report     # explicit
```

Exit `0` unless the conventions lane reports error-severity violations (exit `1`). The analysis lanes are advisory and never affect the exit code.

### Scoping the report (`--exclude`)

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--exclude <glob> [<glob> ...]` | string (repeatable, space- or comma-separated) | — | Extra globs dropped from every analysis lane **and** from the file/LOC header. |

Use it when the tree contains vendored templates, downloaded reference material, or a second checkout that would otherwise dominate the analysis lanes:

```bash
konpy report --exclude 'vendor/**,downloads/**'      # comma-separated
konpy report --exclude 'vendor/**' 'downloads/**'    # space-separated
konpy report --exclude 'vendor/**' --exclude 'docs/**'  # repeatable
```

Notes:

- Patterns are **additive** on top of the always-applied vendored/build excludes; `--exclude` never widens the default scope.
- Commas and whitespace inside `{...}` alternation are preserved, so `--exclude '**/{tests,docs}/**'` stays one pattern. Quote your patterns so the shell does not glob-expand them first.
- Every lane is scoped consistently, so the header count, duplication, coverage, and unused-code findings all describe the same file set. This matters for the unused lane in particular: excluding a tree also removes its *references*, so dead code a vendored copy was masking becomes visible.
- The **conventions lane is not affected**. It is scoped by `konpy.json` (`paths`, `excludeFiles`, `unusedCode.include`), so `konpy report --exclude ...` and `konpy check` continue to agree on conventions.
- This is a flag rather than a config key, so bare `konpy` keeps reporting the whole tree. `konpy --exclude ...` without the subcommand implies `check`, which has no `--exclude`; write `konpy report --exclude ...`.

## `init`

Writes a strict starter `konpy.json` into the current directory. The template is opinionated about what a best-in-class Python codebase looks like — 17 conventions plus `unusedCode`:

- **Layout**: `pyproject.toml` + `src/` layout at the root, every `src/` package has `__init__.py`.
- **Barrel purity**: `__init__.py` files never contain business logic — only docstrings, imports, `__all__`, and re-export aliases (`areBarrelFiles`), and each carries a module docstring.
- **Typing**: no `typing.Any`, public functions annotate params and returns, no identity-less anonymous record annotations (`restrictAnnotations`).
- **Docs and API surface**: docstrings on public classes/functions, public modules declare `__all__`, no underscore names in `__all__`.
- **Size and imports**: 300-line module cap, absolute imports only outside barrels.
- **Tests**: modules mirror into `tests/` (`havePairedFile`); underscore-private modules are exempt, tested through their facade.
- **Hygiene**: no `print()` in library code, no TODO/FIXME markers (warning), repeated-literal and duplicate-function ratchets (warning), unused-code detection over `src/`.

On a brand-new empty directory, `konpy init && konpy check` fails on purpose: the first diagnostics walk you into the src layout. Refuses to overwrite an existing `konpy.json` (exit `1`); exits `0` after writing and prints next steps.

```bash
konpy init
```

## `docs`

Prints the bundled reference docs to stdout — they ship inside the wheel, so a pip/uv install has the full config-language reference offline, without a repo checkout.

```bash
konpy docs               # list available topics
konpy docs predicates    # print docs/reference/predicates.md
konpy docs configuration # the full konpy.json reference
```

An unknown topic exits `1` and lists the available topics on stderr.

## `extract-rules`

Explicitly asks a local agent CLI to convert prose rules into a reviewable [`ReusableConventionsPackageV1`](./reusable-conventions.md) proposal.

```bash
konpy extract-rules docs/team-style-guide.md
konpy extract-rules docs/team-style-guide.md -o packs/team-style.json
konpy extract-rules docs/team-style-guide.md --agent codex --report unmapped.md
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
      "reason": "Formatting is enforced by Ruff, not konpy predicates."
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
konpy extract-rules rules.md
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

A successful run writes only the reusable convention pack proposal. It never edits or creates `konpy.json`.

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

## `infer`

Mines the current repository for candidate structural conventions using deterministic heuristics over the same AST/filesystem walkers `check` uses, and emits a reviewable proposal — no agent call, no existing-config awareness, and it never touches `konpy.json`.

```bash
konpy infer
konpy infer -o konpy.infer.pack.json -r infer-report.md
konpy infer --heuristic export-suffix --heuristic paired-test-file
konpy infer --min-confidence 0.8 --min-support 5
```

Eight independent heuristics each look for a deterministic signal — a suffix/export pattern, a test-pairing convention, docstring coverage, type-annotation coverage, `__init__.py` barrel purity, absolute-vs-relative import dominance, repeated-literal cleanliness, and duplicate-function cleanliness — and, for every signal whose sample size and pass-rate clear the configured thresholds, propose one `severity: "warning"` convention. The duplication heuristics are clean-only ratchets: they propose only when the current scope already has zero violations under the default predicate thresholds. The emitted proposal is validated against `ReusableConventionsPackageV1` — the same reviewable-pack contract `extract-rules` emits (`{"conventionSpecVersion": "v1", "conventions": [...]}`) — never a `RawConfigV1`/`konpy.json`-shaped document. See [Inferring conventions](../guides/inferring-conventions.md) for the full heuristic reference and tuning guidance.

### Output-channel contract

The **proposed pack** is the primary artifact: stdout by default, or the `--output`/`-o` path. The **confidence/violators report** is secondary: stderr by default, or the `--report`/`-r` path. This makes `konpy infer > konpy.infer.pack.json` always work, and keeps the two artifacts independently redirectable:

```bash
konpy infer > konpy.infer.pack.json      # pack on stdout, report on stderr
konpy infer -o konpy.infer.pack.json     # confirmation on stdout, report on stderr
konpy infer -o out.json -r report.md          # confirmations on stdout, both bodies in files
```

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--include <glob>` | string (repeatable) | `**/*.py` | Glob(s) of files to scan |
| `--exclude <glob>` | string (repeatable) | — | Glob(s) to exclude from scanning |
| `--test-glob <glob>` | string (repeatable) | `tests/**`, `test_*.py`, `*_test.py`, `conftest.py` | Glob(s) identifying test files |
| `--min-confidence <n>` | float in `[0.0, 1.0]` | `0.9` | Minimum support/total ratio required to emit a proposal (`>=`, inclusive) |
| `--min-support <n>` | integer `>= 1` | `3` | Minimum sample size (denominator) required before a signal is considered at all |
| `--max-violators <n>` | integer `>= 0` | `10` | Maximum violator paths listed per proposal in the report (full-precision internally; only display is truncated) |
| `--heuristic <name>` | string (repeatable) | all nine | Restrict to specific heuristics: `export-suffix`, `paired-test-file`, `docstring-coverage`, `annotate-functions-coverage`, `barrel-usage`, `import-dominance`, `repeated-literals`, `duplicate-functions`, `file-length` |
| `--format <format>` | `text` \| `markdown` \| `json` | `text` | Report format |
| `-o, --output <path>` | string | — (stdout) | Write the proposed pack here instead of stdout |
| `-r, --report <path>` | string | — (stderr) | Write the report here instead of stderr |

### Exit codes

- `0` — a normal run, including a run that proposes zero conventions (e.g. nothing cleared the thresholds, or `--include` matched no files).
- `1` — invalid flags (out-of-range `--min-confidence`/`--min-support`/`--max-violators`, an unknown `--heuristic` name), or an I/O/internal-validation failure writing `--output`/`--report`.

### Review workflow

`infer` never edits `konpy.json`. After generation:

1. inspect the proposed pack and the report side by side — every proposal lists its `support/total` counts and the (possibly truncated) violator file list;
2. delete or narrow any proposal that does not reflect an intentional convention;
3. only then merge the surviving conventions into your real `konpy.json` (e.g. via `extends`, or by hand-copying entries).

Every emitted convention hard-codes `severity: "warning"`, so once you have copied surviving conventions into a real `konpy.json` (directly, or via `conventionSources`/`extends` pointing at the saved pack file), a first `konpy check` never hard-fails CI before you have reviewed it. The pack itself is not a valid `konpy.json` and `check`/`validate` will reject it if pointed at it directly — that rejection is intentional, not a bug.

## `explain`

Loads `konpy.json`, resolves it exactly like `check`/`validate` do (after `extends`/`disable`/`conventionSources`/`plugins`), and renders every configured convention plus the `unusedCode` settings as concise Markdown (default) or plain-text guidance — suitable for pasting into `CLAUDE.md` or an equivalent agent instructions file so a code-writing agent follows the rules *before* writing code, instead of only being caught by `konpy check` afterwards.

`explain` never touches the filesystem being linted and performs no diagnostic evaluation: it does not glob files, parse Python source, or run any predicate. `--diagnostic-level`, `--max-diagnostics`, `--colors`, `--error-on-warnings`, and `--show-suppressed` do not apply to it and are not accepted. It always renders every configured convention regardless of severity.

```bash
konpy explain
konpy explain --format text
konpy explain --config-path path/to/konpy.json > CLAUDE.md
```

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--config-path <path>` | string | `konpy.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but **always errors as unsupported** in the Python port. Use `--config-path` instead |
| `--format <md\|text>` | `md` \| `text` | `md` | Output format |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, overriding any entry already there. May be passed multiple times |

Output is written to stdout only; there is no `--fix`/`--emit-patch`/file-write flag. Redirect it (`konpy explain > CLAUDE.md`) or copy/paste the relevant sections into your agent instructions file.

Template placeholders (`${name}`, `${name.method(...)}`) inside `paths` or predicate values are rendered **verbatim, unresolved** — there is no per-file match context at explain time, only the resolved config. This is a deliberate scope decision, not a bug.

Sample Markdown output:

```md
# Project conventions

Structural conventions enforced by `konpy`. Follow these before writing or editing Python files in this repository.

## Conventions

- **`documented-service`** (severity: `error`) — paths: `src/service.py`
  - Service modules must be paired and documented.
  - hint: Create the paired test file next to the service module.
  - must: `havePairedFile` tests/test_service.py

## Suppressions

Suppression comments (`konpy: ignore[rule]`) are for approved exceptions only. Never add one without explicit human approval -- see `docs/reference/suppressions.md`. Fix the violation, or ask a human to approve a suppression with a reason.
```

Each convention bullet shows its resolved name (generated the same way `check`'s suppression-comment matching would name it, when no explicit `name` is set), paths, `description`, `hint`, and `severity`, followed by its `must`/`mustNot` predicates. Conventions with multiple `must` blocks label each block by name (or `block N`) so conditional (`if`/`for`/`excludeFiles`) rules stay unambiguous. When `unusedCode` is configured, a `## Unused code` section lists the fully resolved include/exclude globs, entrypoint files, registry decorators, hook names, model base classes, and any explicit `allow` list — including framework presets, not just what you wrote in `konpy.json`. Every render ends with a standing `## Suppressions` note reiterating the [suppression consent policy](./suppressions.md#ai-agents): agents must never add a `# konpy: ignore[...]` comment without explicit human approval.

## `hook`

Runs an agentic `PostToolUse` verification hook for Claude Code or Codex. Unlike every other command, `hook` reads its input as a JSON hook payload on stdin rather than operating on `konpy.json` or the filesystem directly, and it is the only subcommand that ever shells out to an agent as a side effect of normal use (`extract-rules` only does so when invoked explicitly).

```bash
konpy hook --agent claude --match 'src/**/*.py' --prompt 'Docstrings are not aspirational: verify each function body actually does what its docstring claims.'
konpy hook --agent codex --match 'src/**/*.py' --match 'tests/**/*.py' --prompt '...' --timeout 120
```

It is meant to be wired into a coding agent's own hook config (Claude Code `.claude/settings.json`, Codex `.codex/hooks.json`), not run interactively — see [Agentic verification hooks](../guides/hooks.md) for setup snippets and worked examples.

### What it does

1. Reads a hook payload as JSON from stdin (the shape Claude Code and Codex both send to hook commands).
2. Skips silently (exit 0) unless the payload is a write-shaped tool call (`Write`/`Edit`/`MultiEdit` for Claude, `apply_patch` for Codex) on a path matching `--match`.
3. Builds a verification prompt from `--prompt` plus the matched file path and spawns the chosen `--agent` read-only, asking it to return one JSON verdict object.
4. Turns that verdict into a hook-protocol exit code.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--match <glob>` | string (repeatable) | — (matches nothing) | Glob pattern(s) to filter the written/edited file path against |
| `--prompt <text>` | string | — | Natural-language verification instruction for the agent. Required; a missing value fails open with exit code 1 rather than a CLI usage error, so exit code 2 stays reserved for a verified fail verdict |
| `--agent <claude\|codex>` | string | — | Verifier agent CLI to use. Required; a missing or invalid value (including a stale `auto` copied from `extract-rules`, which isn't accepted here) fails open with exit code 1 |
| `--timeout <seconds>` | float | `300.0` | Timeout for the verifier agent subprocess |
| `--log <path>` | string | — | Append verified fail verdicts as JSONL for later `hook-propose`. Logging is fail-open and never changes the hook exit-code contract |

### Exit-code contract

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | pass, or skipped — sentinel env set, non-write tool, no extractable path, no `--match` hit, blank/unparseable payload | silent |
| `2` | verdict is **fail** — reserved exclusively for this | reasons written to stderr (the host feeds this back to the model) |
| `1` | infra fail-open — agent binary not on `PATH`, subprocess timeout or nonzero exit, unparseable agent output, missing/bad `--prompt`/`--agent` | one line on stderr, non-blocking |

Exit `2` is never used for infra trouble, and exit `1` is never used for an actual fail verdict.

### Recursion guards

A `claude -p` or `codex exec` spawned from inside the hook would, by default, inherit the very same hooks — including this one. Two guards prevent that:

- **Sentinel env var.** `konpy hook` sets `KONPY_HOOK_ACTIVE=1` in the child agent's environment before spawning it. If `konpy hook` ever sees that variable already set — because it's running inside a nested agent invocation — it exits 0 immediately without doing any work.
- **Read-only child.** The verifier agent is invoked with flags that keep it from writing anything: `claude` gets `--allowedTools Read Grep Glob` plus an inline `--settings '{"hooks":{}}'` (no temp file; unlisted tools are auto-denied in `-p` mode); `codex` gets `--sandbox read-only`. A child that can't write can't re-trigger a `PostToolUse` write hook in the first place.

### Suppressions

A fail verdict's reasons are self-correction feedback, same as any other linter/test failure surfaced through a hook. Nothing about `hook`'s prompt or exit-code contract instructs an agent to add a `# konpy: ignore[...]` comment — see the [suppression consent policy](./suppressions.md#ai-agents), which still applies in full if the feedback ever seems to call for a suppression rather than a fix.

`konpy hook` never invokes `konpy check`, `konpy gate`, or `konpy validate`, and vice versa; the mechanisms are independent. See [Which hook mechanism should I use?](../guides/hooks.md#which-hook-mechanism-should-i-use) for the comparison with deterministic `PostToolUse` checking and deterministic `PreToolUse` gating.

## `gate`

Runs a deterministic Claude Code `PreToolUse` gate against proposed write content. Unlike `check`, `gate` reads a hook payload from stdin. Unlike `hook`, it never invokes an agent. It reconstructs the proposed post-write content for Claude Code `Write`, `Edit`, and `MultiEdit`, overlays that content in memory at the real project path, and runs the normal convention engine in-process before the write lands.

```bash
konpy gate --match 'src/**/*.py'
konpy gate --match 'src/**/*.py' --match 'tests/**/*.py' --error-on-warnings
konpy gate --diagnostic-level error --max-diagnostics 20
```

It is meant to be wired into Claude Code `.claude/settings.json` as a `PreToolUse` hook — see [Claude Code hook integration](../guides/claude-code-hook.md#a-pretooluse-gate-with-konpy-gate).

### What it does

1. Reads a Claude Code hook payload as JSON from stdin.
2. Skips silently unless the payload is a Claude Code write-shaped tool call: `Write`, `Edit`, or `MultiEdit`.
3. Extracts the target path and filters it through `--match`. If `--match` is omitted, every target path is gated.
4. Reconstructs the proposed post-write content:
   - `Write` uses `tool_input.content` as the full file body.
   - `Edit` reads the current file content, then applies one `old_string` → `new_string` replacement, honoring `replace_all`.
   - `MultiEdit` folds each edit in order.
5. Runs the normal deterministic convention check through an overlay filesystem, scoped to the reconstructed target path.
6. Allows clean proposed content with exit `0`, or blocks verified convention violations with exit `2` and check-compatible JSON diagnostics on stderr.

Codex `apply_patch` reconstruction is out of scope in v1. Unsupported tools, malformed payloads, and unreconstructable edits fail open with exit `0`.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--match <glob>` | string (repeatable) | — (gates every target path) | Glob pattern(s) to filter proposed write paths against. Unlike `konpy hook`, omitting this means all target paths are gated |
| `--config-path <path>` | string | `konpy.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but **always fails open as unsupported** in the Python port. Use `--config-path` instead |
| `--diagnostic-level <level>` | `warning` \| `error` | `warning` | Minimum severity to evaluate. `error` skips warning-severity conventions and suppression hygiene warnings, matching `check` |
| `--error-on-warnings` | boolean | `false` | Block proposed writes on warnings as well as errors |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, matching `check` semantics |
| `--max-diagnostics <n>` | integer | `100` | Maximum unsuppressed diagnostics to include in the blocking JSON payload |

`gate` has no `--format` flag. Blocking output is always the same JSON object shape as `konpy check --format json`, written to stderr with a trailing newline.

### Exit-code contract

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | allow, skipped, clean proposed content, warnings-only without `--error-on-warnings`, unreconstructable payload, or fail-open config/runtime problem | usually silent; config/runtime failures write one `konpy gate: warning: <detail>` line to stderr |
| `1` | unrecognized `konpy gate` CLI arguments only | one stderr line; non-blocking misconfiguration |
| `2` | verified convention violation in proposed content, or warnings when `--error-on-warnings` is set | check-compatible JSON diagnostics on stderr |

Exit `2` is reserved exclusively for verified convention diagnostics. Config-load errors, invalid placeholders, unsupported `--config-package`, malformed payloads, runner exceptions, and unreconstructable edits never exit `2`; they fail open with exit `0`. The only exit `1` path is the CLI unknown-arguments guard, so a misconfigured gate is never mistaken for a convention block.

### JSON blocking output

On exit `2`, stderr is the same parseable JSON object produced by `konpy check --format json`:

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
  },
  "truncation": {
    "shown": 1,
    "omitted": 0
  }
}
```

`diagnostics` is truncated by `--max-diagnostics`, while `summary.errors` and `summary.warnings` remain the full pre-truncation totals, exactly like `check`.

### Recursion

`gate` does not spawn a subprocess, so it does not use the `KONPY_HOOK_ACTIVE` recursion sentinel from `konpy hook`. Setting that environment variable does not disable `gate`.

## `hook-propose`

Promotes logged `konpy hook` fail findings into a reviewable [`ReusableConventionsPackageV1`](./reusable-conventions.md) proposal plus an unmapped report. It never edits `konpy.json`.

```bash
konpy hook-propose
konpy hook-propose .konpy/hook-findings.jsonl
konpy hook-propose findings.jsonl -o packs/ratchet.json --report reports/ratchet-unmapped.md
konpy hook-propose --agent codex --model gpt-5-codex --timeout 600
```

### Argument

| Argument | Default | Description |
| --- | --- | --- |
| `[findings-path]` | `.konpy/hook-findings.jsonl` | JSONL log written by `konpy hook --log` |

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `-o, --output <path>` | string | `packs/hook-proposals.json` | Path for the generated reusable convention pack proposal |
| `--agent <agent>` | `auto` \| `claude` \| `codex` | `auto` | Agent CLI to invoke |
| `--report <path>` | string | — | Write the unmapped-rules report to a file instead of printing it to stdout |
| `--model <model>` | string | `sonnet` | Model passed through to the agent CLI as `--model` |
| `--timeout <seconds>` | float | — | Timeout for the proposal agent subprocess |

### Behavior

`hook-propose` reads valid `fail` findings from the JSONL log, skips invalid/corrupt/non-fail lines with warnings, groups valid findings by exact hook prompt, and sends the aggregated evidence to the selected agent. The agent must return one JSON object:

```json
{
  "pack": {
    "conventionSpecVersion": "v1",
    "conventions": []
  },
  "unmapped": []
}
```

The returned `pack` is validated with the reusable-conventions schema before anything is written. The generated pack is a proposal for human review; wire accepted conventions into `konpy.json` manually with `conventionSources`.

If the findings file is missing or contains no valid fail findings, the command exits `0`, prints a calm “No fail findings to promote” message, invokes no agent, and writes nothing.

### Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Successful proposal, or no valid fail findings to promote |
| `1` | Agent selection/invocation failure, unreadable predicate reference, invalid agent JSON, invalid response contract, invalid proposed pack, or output/report write failure |

On failure, `hook-propose` writes no proposal pack. If report writing fails after a pack write, the command exits `1` and leaves the already-written proposal in place, matching `extract-rules` behavior.

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

GitHub Actions annotations (`::error file=...,line=...::message` and `::warning ...`). Auto-selected when `GITHUB_ACTIONS=true` is set in the environment, so `konpy check` in a GitHub workflow needs no extra flags.

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
  },
  "truncation": {
    "shown": 2,
    "omitted": 0
  }
}
```

`diagnostics` contains unsuppressed diagnostics only, truncated to `--max-diagnostics`. `suppressed` contains diagnostics suppressed by source comments. `severity` is `"error"` or `"warning"`. `line`, `description`, `hint`, `expected`, `found`, and `fixHint` are all omitted (never emitted as `null`) when not applicable to that diagnostic — see [Diagnostic intent and fix direction](#diagnostic-intent-and-fix-direction).

`summary.errors`/`summary.warnings` are always the full pre-truncation totals — they never shrink when `diagnostics` is truncated. `truncation` is always present: `shown` is `diagnostics.length`, `omitted` is how many unsuppressed diagnostics were cut by `--max-diagnostics` (`0` when nothing was truncated). See [Truncation](#truncation).

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

`expected`/`found`/`fix_hint` are populated by the predicates where they can be expressed unambiguously: `exportClasses`, `exportConstants`, `havePairedFile`, `haveDocstrings`, `annotateFunctions`, `restrictAnnotations`, `restrictRepeatedLiterals`, `restrictDuplicateFunctions`, `importFrom`, `importFrom*`/`importTypes*` (current-dir/parents/externals groups), and `matchContent`. Other predicates leave these fields `None` rather than guessing — a vague hint is worse than no hint.

All five fields are additive and optional everywhere they appear: omitted from JSON when absent (never emitted as `null`), and producing no extra line/cell in `default`/`markdown` output when absent. `fix_hint` is data only — konpy never applies it automatically and never emits suppression comments; see [Suppressions](./suppressions.md) for the consent policy on machine-authored changes.

## Truncation

When the number of unsuppressed diagnostics exceeds `--max-diagnostics`, only the first `n` unsuppressed diagnostics are printed and a truncation summary is appended:

```text
... and 437 more diagnostics (use --max-diagnostics to see more)
```

The exit code still reflects all unsuppressed violations — only the printed output is truncated. Suppressed counts are computed from the full run result and are not truncated.

Under `--format json`, the `diagnostics` array is truncated the same way, but `summary.errors`/`summary.warnings` are always the full pre-truncation totals, and a top-level `truncation: {shown, omitted}` key (always present, `omitted: 0` when nothing was cut) makes truncation explicit for machine consumers instead of leaving it to be inferred from `diagnostics.length` — see [`json`](#json).
