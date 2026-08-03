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
| `konpy review` | Run an advisory `PostToolUse` model verification; findings never block |
| `konpy hook` | Deprecated: blocking `PostToolUse` model verification; use `review` or `gate` instead |
| `konpy hook-propose` | Promote logged hook findings into a reusable convention pack proposal |
| `konpy improve` | Ask a read-only agent to propose a diff for one duplication finding; never applies it |
| `konpy verify` | Run the config-declared verification-step roster (the `verify` section) |
| `konpy help` | Show a quick reference of all commands and options |
| `konpy version` | Print the version number |

Bare `konpy` runs the zero-config report; options without a subcommand (e.g. `konpy --files a.py`) still imply `check`. `konpy help` prints the full help with a getting-started brief. `konpy --version` prints the version. There is no `update` command.

Rule extraction is never implicit: `konpy` only shells out to an agent when you run `konpy extract-rules`, `konpy hook-propose`, or `konpy improve` directly, or when a `konpy review`/`konpy hook` invocation actually matches a write event. `konpy gate` runs deterministic checks in-process and never shells out to an agent.

## `check`

Loads `konpy.json`, runs every convention against the codebase, and reports violations.

```bash
konpy check
konpy check --format=json --max-diagnostics=1000
konpy check --error-on-warnings --diagnostic-level error
konpy check --show-suppressed
konpy check --files src/service.py
konpy check --changed
konpy check --write-baseline
konpy check --show-baselined
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
| `--baseline <path>` | string | `konpy.baseline.json` next to the resolved config file | Baseline file path, used for both reading and `--write-baseline`. Read auto-discovery needs no flag: a `konpy.baseline.json` at the default path is picked up automatically |
| `--write-baseline` | boolean | `false` | Record every current violation into the baseline file and exit `0` (recording mode) instead of running a normal check. See [Baseline and the ratchet](#baseline-and-the-ratchet) |
| `--show-baselined` | boolean | `false` | List diagnostics hidden by the baseline in human-readable output, the way `--show-suppressed` lists suppressed ones |

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

- `0` — no unsuppressed errors (warnings allowed unless `--error-on-warnings` is set), or a `--write-baseline` run (always `0`, recording mode).
- `1` — a config error, a malformed baseline file, any unsuppressed error-severity diagnostic, or unsuppressed warnings when `--error-on-warnings` is set.

Suppressed errors do not fail the command. Suppressed warnings do not fail `--error-on-warnings`. Suppression hygiene diagnostics, such as unused suppressions, are normal warnings and do fail when `--error-on-warnings` is set. Stale baseline entries never fail the command, even with `--error-on-warnings` set — see below.

### Baseline and the ratchet

A baseline records today's violations so `check` fails only on *new* ones, without editing `konpy.json` or touching a single line of source. It's the brownfield adoption tool: turn on a rule (or a whole stricter config) against an existing codebase, and get a clean `check` immediately instead of a wall of pre-existing debt.

```bash
konpy check --write-baseline               # record every current violation, exit 0
konpy check                                # auto-discovers konpy.baseline.json, fails only on new violations
konpy check --baseline konpy.strict.baseline.json --write-baseline   # explicit path
```

`--write-baseline` runs the check as usual — suppressions still apply — then writes every remaining violation (errors and warnings alike) to the baseline file and exits `0` unconditionally: it's a recording action, not a pass/fail one. Plain `konpy check` auto-discovers `konpy.baseline.json` next to the resolved config with no flag needed, so a baseline committed to the repo just works in CI. `--baseline <path>` overrides the default path for both reading and writing.

Counts only ever move down. A `(file, convention)` group's baselined count can shrink for two reasons: the ratchet mechanically shrinking as you improve code, or `--write-baseline` explicitly ratcheting the floor down after you fix debt. If a baseline entry ever needs a higher count than what's recorded, `check`/`--write-baseline` say so loudly — a `baseline: raised <file>/<convention> from X to Y` warning on `--write-baseline`, one per raised key — because a baseline is supposed to be a floor, not a ceiling that quietly moves to match whatever the code does. Coverage-style rules (`haveDocstrings`, `annotateFunctions`) ratchet upward for free this way: each file's violation count can only fall as you add docstrings or annotations, so the baseline never needs raising for them without a warning telling you so.

A baseline entry recorded above what's currently found is stale — you fixed something and the floor hasn't caught up. `check` reports it as a warning under the `baseline` label, unconditionally (no flag needed), and it never fails the run even under `--error-on-warnings`: penalizing the exact moment debt goes down would undercut the point of ratcheting it. Run `--write-baseline` again to clear the warning.

`--show-baselined` reveals what's hidden, rendering baselined diagnostics the way `--show-suppressed` renders suppressed ones. `--format json` always includes the full `baselined`/`baselineStale` detail regardless of that flag — see [`json`](#json).

`konpy gate` accepts the same `--baseline <path>` flag (auto-discovery included): a pre-existing baselined violation never blocks a proposed write, only a new one does.

See [the ratchet guide](../guides/ratchet.md) for the full brownfield adoption flow.

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

Parse-time interpreter warnings from analyzed source (`SyntaxWarning` for an invalid escape sequence, for instance) are suppressed: konpy reports parse problems its own way, via the `N unreadable/unparsable files skipped` note, rather than interleaving CPython's warnings — about code you may not own — with its report.

- **Conventions** — when `konpy.json` exists: the standard check runs and its errors/warnings summarize into the report (an invalid config is reported without killing the other lanes). Without one, a built-in **default trio** runs instead: barrel `__init__.py` files (`areBarrelFiles`), no `typing.Any` annotations, and modules ≤300 lines — the layout-agnostic subset of the `konpy init` starter. Test files are exempt from the latter two, and example/tutorial trees (`examples/`, `docs_src/`, `samples/`) are exempt from all three, matching the duplication lane's example-awareness. Default findings are warning-severity and advisory: they never change the report's exit code, respect inline suppressions, and skip vendored/generated/gitignored files the same way the analysis lanes do. `konpy init` upgrades them to the full, enforceable strict starter.
- **Duplication** — repeated string literals (≥8 chars, more than 2 occurrences) and duplicate function implementations (≥4 statements, alpha-renamed fingerprints), tests excluded.
- **Unused code** — the [unused-code engine](unused-code.md) at defaults; test files feed the reference index but never carry findings.
- **External tools** — ruff, basedpyright, and import-linter, each run as an independent subprocess (see [External tools](#external-tools) below).
- **Coverage** — docstring coverage for public modules/classes/functions and fully-annotated public function ratio; `konpy infer` turns these into enforceable ratchet proposals.

Sections render in this order — conventions first (it's config policy, not a finding), then the analysis lanes in blast-radius order: cross-component duplication compounds fastest, dead code second, external-tool and style debt last.

Generated code is detected per file by generator banners in the first lines (`@generated`, `auto-generated`, `DO NOT EDIT`, `# Generated by ...` comments — Fern/OpenAPI clients, protobuf stubs, Django migrations), minus any paths listed in a `.fernignore` (those are hand-maintained even when they carry a stale banner). Generated files are counted in the report header, feed the unused lane's reference index without carrying findings (so hand-written code called only from generated code stays used), are excluded from coverage stats, and duplicate groups confined to them are tagged `[generator template]` instead of being presented as copy-paste.

Duplicate groups whose members all live under example or documentation directories (`examples/`, `docs_src/`, `docs/`, `samples/`) are tagged `[example/docs code]`: tutorial snippets repeat setup code so each one stands alone. A duplicate spanning example and production code is not tagged — that one is real.

Two more duplication-lane refinements: repeated literals dominated by **mapping-key positions** (dict-display keys, subscript indexes, `.get()`/`.pop()`/`.setdefault()` arguments — ≥90% of occurrences) are tagged `[mapping keys]` and ranked after everything else, because serialization boundaries — OpenSearch mappings, IAM policies, API payloads — repeat keys by protocol necessity. And a duplicate-function group whose members carry different names lists them (`iter_error_chain a.k.a. iter_retry_error_chain`) so a rename can't hide a copy-paste. Groups whose members span more than one component (a member's top-level directory, or the package directory one level under a `src`/`lib` root) are tagged `[cross-component]` and ranked ahead of same-component groups regardless of size — a duplicate that already crossed a package boundary is the one most likely to drift further before anyone notices.

```bash
konpy            # bare invocation
konpy report     # explicit
```

### External tools

Three lanes run as independent subprocesses, concurrently with each other and with the rest of the report, so the wall-clock cost is the slowest one rather than their sum:

| Tool | Runs when | Findings |
| --- | --- | --- |
| [ruff](https://docs.astral.sh/ruff/) | always | rule violations from `ruff check --output-format json`; top 5 rule codes by frequency, with the first occurrence's message |
| [basedpyright](https://docs.basedpyright.com/) | always | `errorCount + warningCount` from `basedpyright --outputjson`; top 5 rule names by frequency |
| [import-linter](https://import-linter.readthedocs.io/) | contracts are configured | broken-contract count parsed from `lint-imports`'s `Contracts: N kept, M broken` summary line; broken contract names as top items |

"Contracts are configured" means any of: a `[tool.importlinter]` table in `pyproject.toml`, an `[importlinter]` section in `setup.cfg`, or an `.importlinter` file at the project root — see [Import boundaries](../guides/import-boundaries.md) for what to put there. Without one, import-linter never runs and the lane reports `no config` rather than a false "clean".

Every lane degrades to a single status line instead of affecting the report's exit code or blocking the others:

| Status | Meaning |
| --- | --- |
| `not installed` | the binary isn't in the target repo's `.venv/bin` or on `PATH` — install the lane's tool via `pip install "konpy[quality]"` |
| `no config` | import-linter only: no contracts configured |
| `timed out` | the subprocess exceeded its timeout (60s by default) |
| `error` | an unexpected exit code or output konpy couldn't parse; the note carries the tool's first stderr line |

Each tool resolves to the target repo's own `.venv/bin` copy when one exists (konpy usually runs as an isolated tool install whose `PATH` never contains it), falling back to a plain `PATH` lookup otherwise. Neither those binaries nor a project's `pyproject.toml`/`setup.cfg`/`.importlinter` are konpy config — there is no `--exclude`-style flag for this section.

Exit `0` unless the conventions lane reports error-severity violations (exit `1`). The analysis lanes are advisory and never affect the exit code.

### Scoping the report (`--exclude`)

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--exclude <glob> [<glob> ...]` | string (repeatable, space- or comma-separated) | — | Extra globs dropped from every analysis lane **and** from the file/LOC header. |

Use it when the tree contains vendored templates, downloaded reference material, or a second checkout that would otherwise dominate the analysis lanes:

```bash
konpy --exclude vendor,downloads                     # bare dir names, no subcommand
konpy report --exclude 'vendor/**,downloads/**'      # comma-separated
konpy report --exclude 'vendor/**' 'downloads/**'    # space-separated
konpy report --exclude 'vendor/**' --exclude 'docs/**'  # repeatable
```

Notes:

- `--exclude` without a subcommand routes to `report` rather than `check`, so `konpy --exclude vendor` works as typed. Every other flags-only invocation still implies `check`.
- A pattern with **no glob metacharacters** is treated as a path prefix and also matches everything beneath it, so `--exclude vendor` behaves like `--exclude 'vendor/**'`. Pass a glob when you want exact matching.
- A pattern that matches **nothing** prints a warning to stderr (`--exclude pattern matched nothing: ...`). A misspelled exclude is otherwise indistinguishable from a correct one, since the report just comes back unscoped.
- Patterns are **additive** on top of the always-applied vendored/build excludes; `--exclude` never widens the default scope.
- Commas and whitespace inside `{...}` alternation are preserved, so `--exclude '**/{tests,docs}/**'` stays one pattern. Quote globs so the shell does not expand them first.
- Every lane is scoped consistently, so the header count, duplication, coverage, and unused-code findings all describe the same file set. This matters for the unused lane in particular: excluding a tree also removes its *references*, so dead code a vendored copy was masking becomes visible.
- The **conventions lane is not affected**. It is scoped by `konpy.json` (`paths`, `excludeFiles`, `unusedCode.include`), so `konpy report --exclude ...` and `konpy check` continue to agree on conventions.
- The **external-tool lanes are not affected** either: ruff, basedpyright, and import-linter each run over the whole project through their own configuration (`pyproject.toml`, etc.), not through konpy's file collection, so `--exclude` has no effect on them. Use each tool's own exclude settings if you need to scope them.
- This is a flag rather than a config key, so bare `konpy` keeps reporting the whole tree. `konpy --exclude ...` without the subcommand implies `check`, which has no `--exclude`; write `konpy report --exclude ...`.

### Vendor and template detection (`--include-vendored`)

Multi-service repos routinely carry trees that are not the codebase under review: cookiecutter scaffolds, vendored snapshots of a dependency, and gitignored build junk. Left alone these dominate file counts, unused-code findings, and coverage percentages. The report detects three kinds of file and, by default, drops them from every in-process lane (the file/LOC header, duplication, coverage, and unparsable-file accounting):

- **Template** — any path segment containing both `{{` and `}}` (a cookiecutter variable directory), or any file under a directory that directly holds a `cookiecutter.json`.
- **Vendored** — a path segment named `downloads`, `vendor`, `vendors`, `third_party`, `thirdparty`, or `_vendor`, or a `name@revision` snapshot-dir segment (the part after `@` is at least 7 hex-ish characters, so `pkg@main` doesn't match but `libs-x@a1b2c3d` does).
- **Gitignored** — whatever `git ls-files --others --ignored --exclude-standard` reports, when the report's root is a git worktree. Not a git repo, or `git` isn't on `PATH`: this rule contributes nothing.

A file matching more than one rule is only counted once, by precedence template > vendored > gitignored.

Dropped files are still fed to the unused-code engine as reference-only sources — the same mechanism generated code (above) uses: they can never carry a diagnostic themselves, but code they reference stays reachable, so a hand-written helper called only from a vendored copy isn't reported dead. A dead definition *inside* a dropped tree never surfaces at all, since the file is never parsed into the report's own structures.

The header gains a `(N vendored/template/ignored)` count next to the generated count, and — for template/vendored matches only, since a gitignored file isn't necessarily part of a "tree" — a note listing up to 3 matched directory roots:

```
■ konpy report · 140 files (12 vendored/template/ignored) · 9,300 LOC · ...
  note: skipped vendor/template trees: downloads/, vendor/
```

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--include-vendored` | boolean | off | Count template/vendored/gitignored files like any other source instead of dropping them. |

`--include-vendored` disables the dropping, not the detection: those files are parsed and counted normally, fully eligible for unused-code findings, but duplicate groups confined to a template or vendored tree still carry their `[generator template]` / `[vendored]` label — useful when a config deliberately scopes duplication checks over such a tree. Detection is not affected by `--exclude`, and vice versa: `--exclude` is caller-supplied scoping, this is a built-in default.

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

### `init --agents`

Scaffolds the proven agent-loop shape in one command: the starter `konpy.json` above plus a `verify` roster (`konpy-validate`, `konpy-check`), `AGENTS.md` (a short hand-written intro sentence, then a `<!-- konpy:generated-guidance:start/end -->` block rendered in-process from that `konpy.json` — the same rendering `konpy explain` uses), and `.claude/settings.json` (a `PreToolUse` `konpy gate` hard gate plus a `PostToolUse` `konpy review` advisory check, both matching `**/*.py` — see [the hooks guide](../guides/claude-code-hook.md)).

Every artifact is created only if absent — an existing `konpy.json`, `AGENTS.md`, or `.claude/settings.json` prints a `skipped (exists): <path>` line and is never modified. The one exception is `.gitignore`: if one exists and lacks a `.konpy/` entry (where `konpy review --log` writes hook findings), it's appended in place; a missing `.gitignore` is not created. Exits `0` if anything was written or the `.gitignore` was updated, `1` if every artifact was already in place.

```bash
konpy init --agents
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

**Deprecated.** `hook` remains for backward compatibility, but blocking a write on a model's verdict is discouraged: its exit `2` asks the host to treat an LLM's opinion as a verification failure, and a model's judgment isn't guaranteed to repeat run over run the way a deterministic check is. Prefer [`konpy review`](#review) for advisory findings that never block, or a deterministic [`konpy gate`](#gate) rule (or a `konpy.json` convention) for anything that must actually stop a write. See [Which hook mechanism should I use?](../guides/hooks.md#which-hook-mechanism-should-i-use).

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
| `--log <path>` | string | — | Append fail verdicts as JSONL (`HookFinding`, `verdict: "fail"`) for later `hook-propose`. Logging is fail-open and never changes the hook exit-code contract |

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

`konpy hook` never invokes `konpy check`, `konpy gate`, or `konpy validate`, and vice versa; the mechanisms are independent. See [Which hook mechanism should I use?](../guides/hooks.md#which-hook-mechanism-should-i-use) for the comparison with the advisory `review` and deterministic `PreToolUse` gating below.

## `review`

Runs an advisory `PostToolUse` model verification for Claude Code or Codex. It shares payload parsing, prompt/rules modes, batching, and recursion guards with `konpy hook` — the difference is the contract: no verdict from `review` ever blocks. Semantic review can produce findings; only a committed deterministic policy or test can produce a verification failure.

```bash
konpy review --agent claude --match 'src/**/*.py' --prompt 'Docstrings are not aspirational: verify each function body actually does what its docstring claims.'
konpy review --agent claude --match '**/*.py' --rules packs/team-style.rules.json --log .konpy/hook-findings.jsonl
```

It is meant to be wired into a coding agent's own hook config (Claude Code `.claude/settings.json`, Codex `.codex/hooks.json`), not run interactively — see [Agentic verification hooks](../guides/hooks.md) for setup snippets and worked examples.

### What it does

1. Reads a hook payload as JSON from stdin (the same shape `konpy hook` reads).
2. Skips silently (exit 0) unless the payload is a write-shaped tool call on a path matching `--match` (and, in rules mode, a rule's own `match`).
3. Builds a verification prompt from `--prompt`, or one batched prompt per matched file from `--rules`, and spawns the chosen `--agent` read-only.
4. Verifies every matched path (or rule batch) to completion — unlike `hook`, a fail verdict does not stop the run early; an agent-run failure or invalid verdict on one path is collected as a warning and doesn't cancel the rest.
5. Writes every finding's reasons to stderr as it goes, then, if at least one finding was produced, emits one `additionalContext` JSON object on stdout summarizing all of them.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--match <glob>` | string (repeatable) | — (matches nothing) | Glob pattern(s) to filter the written/edited file path against |
| `--prompt <text>` | string | — | Natural-language verification instruction for the agent. Exactly one of `--prompt`/`--rules` is required; supplying both, or neither, exits 1 |
| `--rules <path>` | string | — | Semantic-rules package to verify — see [Semantic rules](./semantic-rules.md). Exactly one of `--prompt`/`--rules` is required |
| `--agent <claude\|codex>` | string | — | Verifier agent CLI to use. A missing or invalid value exits 1; an installed-but-unreachable agent binary only warns and exits 0 — a model being unavailable must not fail a write |
| `--model <model>` | string | `sonnet` | Model passed through to the agent CLI as its own `--model` flag |
| `--timeout <seconds>` | float | `300.0` | Timeout for the verifier agent subprocess |
| `--log <path>` | string | — | Append findings as JSONL for later `hook-propose`, using the same `HookFinding` schema (`verdict: "fail"`) `konpy hook --log` writes. Logging is fail-open and never changes the exit code |

### Exit-code contract

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | pass, skip, **findings**, or an unavailable model — a verdict never produces a nonzero exit | pass/skip is silent; findings write reasons to stderr plus one `additionalContext` object to stdout; an unavailable agent writes one `konpy review: warning:` line to stderr and nothing to stdout |
| `1` | local misconfiguration only — both or neither of `--prompt`/`--rules`, a missing/invalid `--agent` value, or an unreadable/invalid `--rules` file | one line on stderr |

`review` never exits `2`. Findings and infrastructure trouble are both advisory; only the exit-`1` misconfiguration cases stop the command from running at all.

### `additionalContext` on stdout

When at least one finding was produced, `review` writes one JSON object to stdout — the shape Claude Code's `PostToolUse` hooks use to inject extra context into the agent's next turn:

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "konpy review findings:\nsrc/service.py: The create_user docstring claims persistence, but the body only validates input."}}
```

In rules mode, each line is prefixed with the failed rule's name:

```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "konpy review findings:\nsrc/service.py: contextual-errors: The ValueError omits the failed operation."}}
```

Each finding renders as one line — `<path>: <reasons>` in prompt mode, `<path>: <rule name>: <reasons>` in rules mode — with multiple reasons joined by `; `. Nothing is written to stdout on a clean pass or a skip.

### Recursion guards

Same two guards as `konpy hook`: the `KONPY_HOOK_ACTIVE` sentinel env var, and a read-only verifier child (`--allowedTools Read Grep Glob` for Claude, `--sandbox read-only` for Codex). See [Recursion guards](#recursion-guards) in the `hook` section above for the full explanation — the mechanism is identical.

### Suppressions

A finding's reasons are self-correction feedback, same as any other linter/test failure surfaced through a hook. Nothing about `review`'s prompt or output instructs an agent to add a `# konpy: ignore[...]` comment — see the [suppression consent policy](./suppressions.md#ai-agents), which still applies in full if the feedback ever seems to call for a suppression rather than a fix.

`konpy review` never invokes `konpy check`, `konpy gate`, or `konpy validate`, and vice versa. See [Which hook mechanism should I use?](../guides/hooks.md#which-hook-mechanism-should-i-use).

## `gate`

Runs a deterministic Claude Code `PreToolUse` gate against proposed write content. Unlike `check`, `gate` reads a hook payload from stdin. Unlike `hook`, it never invokes an agent. It reconstructs the proposed post-write content for Claude Code `Write`, `Edit`, and `MultiEdit`, overlays that content in memory at the real project path, and runs the normal convention engine in-process before the write lands.

```bash
konpy gate --match 'src/**/*.py'
konpy gate --match 'src/**/*.py' --match 'tests/**/*.py' --error-on-warnings
konpy gate --diagnostic-level error --max-diagnostics 20
konpy gate --match 'src/**/*.py' --fail-closed
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
5. Runs the normal deterministic convention check through an overlay filesystem, scoped to the reconstructed target path. `unusedCode` is skipped by default — it's a whole-project scan and by far the most expensive lane, and its findings are warnings by default so they can't change the block/pass outcome unless `--error-on-warnings` is set, in which case it runs.
6. Allows clean proposed content with exit `0`, or blocks verified convention violations with exit `2` and check-compatible JSON diagnostics on stderr.

Codex `apply_patch` reconstruction is out of scope in v1. By default, unsupported tools, malformed payloads, and unreconstructable edits fail open with exit `0`. Pass `--fail-closed` to block instead when a supported write couldn't be verified. See [`--fail-closed`](#--fail-closed) below.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--match <glob>` | string (repeatable) | — (gates every target path) | Glob pattern(s) to filter proposed write paths against. Unlike `konpy hook`, omitting this means all target paths are gated |
| `--config-path <path>` | string | `konpy.json` (project root) | Path to the config file |
| `--config-package <pkg>` | string | — | Accepted for upstream compatibility, but unsupported in the Python port: the resulting config-load error fails open by default, or blocks under `--fail-closed` like any other config-load failure. Use `--config-path` instead |
| `--diagnostic-level <level>` | `warning` \| `error` | `warning` | Minimum severity to evaluate. `error` skips warning-severity conventions and suppression hygiene warnings, matching `check` |
| `--error-on-warnings` | boolean | `false` | Block proposed writes on warnings as well as errors |
| `--placeholder <name:value>` | string (repeatable) | — | Inject a placeholder into every convention's `placeholders` map, matching `check` semantics |
| `--max-diagnostics <n>` | integer | `100` | Maximum unsuppressed diagnostics to include in the blocking JSON payload |
| `--fail-closed` | boolean | `false` | Block (exit `2`) when deterministic verification cannot run against a supported write, instead of failing open |
| `--baseline <path>` | string | `konpy.baseline.json` next to the resolved config file | Baseline file path, auto-discovered the same way `check` does. A pre-existing baselined violation never blocks a proposed write; a new one still does. A malformed baseline is treated exactly like a config-load failure: fails open by default, blocks (exit `2`) under `--fail-closed` |
| `--ruff` | boolean | `false` | Also run `ruff check` against every proposed `.py` write's content. See [`--ruff`](#--ruff) below |

`gate` has no `--format` flag. Blocking output on a verified violation is always the same JSON object shape as `konpy check --format json`, written to stderr with a trailing newline. A `--fail-closed` block for an unverifiable payload writes a single plain-text stderr line instead. See below.

### Exit-code contract

| Exit | Meaning | Output |
| --- | --- | --- |
| `0` | allow, skipped (unsupported tool, or `--match` filtered out every target path), clean proposed content, warnings-only without `--error-on-warnings`, or, without `--fail-closed`, any payload/reconstruction/config/runtime problem | usually silent; a fail-open problem writes one `konpy gate: warning: <detail>` line to stderr |
| `1` | unrecognized `konpy gate` CLI arguments only | one stderr line; non-blocking misconfiguration |
| `2` | a verified convention violation in proposed content, warnings when `--error-on-warnings` is set, or, only with `--fail-closed`, a supported write whose content couldn't be verified at all | check-compatible JSON diagnostics on stderr for a violation; a single `konpy gate: verification unavailable: <detail> (blocking: --fail-closed)` line for an unverifiable payload |

By default (fail-open), exit `2` is reserved exclusively for verified convention diagnostics: config-load errors, invalid placeholders, unsupported `--config-package`, malformed payloads, runner exceptions, and unreconstructable edits all exit `0`. `--fail-closed` blocks a subset of those instead. See [`--fail-closed`](#--fail-closed). Two cases exit `0` in both modes because they were never candidates for verification in the first place: a tool call that isn't `Write`/`Edit`/`MultiEdit`, and target paths that exist but don't match `--match`. The only exit `1` path is the CLI unknown-arguments guard, so a misconfigured gate is never mistaken for a convention block.

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

### `--fail-closed`

By default `gate` fails open: anything it can't deterministically verify allows the write through with exit `0`. `--fail-closed` blocks instead, for a specific list of cases where a supported write payload arrived but verification couldn't run against it:

- The hook payload on stdin isn't parseable JSON, or doesn't validate against the expected shape.
- A `Write`/`Edit`/`MultiEdit` payload has no extractable `tool_input.file_path`.
- The proposed content couldn't be reconstructed (e.g. an `Edit`'s `old_string` isn't found in the current file content).
- The config fails to load: invalid JSON or a schema violation at `--config-path`, or `--config-package` (always unsupported in the Python port, so it always fails this way).
- Preparing or running the check raises any other exception.
- `--ruff` is set, at least one proposed `.py` write matched, and no `ruff` executable is found on `PATH`. See [`--ruff`](#--ruff) below.

```bash
konpy gate --match 'src/**/*.py' --fail-closed
```

Each of these exits `2` with one stderr line naming the reason, not the JSON diagnostics shape used for a real violation:

```
konpy gate: verification unavailable: unable to reconstruct proposed content (blocking: --fail-closed)
```

`--fail-closed` does not change two cases that were never candidates for verification: a tool call outside `Write`/`Edit`/`MultiEdit`, and a target path `--match` doesn't select. Both still exit `0` silently, same as without the flag.

Use `--fail-closed` in a hard-gate repo where "the gate passed" must never quietly mean "the gate didn't run". See [Claude Code hook integration](../guides/claude-code-hook.md#a-pretooluse-gate-with-konpy-gate). Leave it off (the default) if you'd rather let a write through than block every edit when, say, `konpy.json` momentarily has a syntax error mid-refactor.

### `--ruff`

`--ruff` runs `ruff check` against the proposed content of every `.py` write `gate` matched, in addition to the normal convention check — structure and lint in one gate. For each matched `.py` target it spawns one `ruff check --stdin-filename <path> --output-format json -` process with the proposed content on stdin, so ruff resolves the target repo's own `pyproject.toml`/`ruff.toml` exactly as it would checking a real file at that path; no separate ruff config wiring is needed.

```bash
konpy gate --match 'src/**/*.py' --ruff
```

Findings are converted to error-severity diagnostics — `conventionName: "ruff"`, `predicateName` the rule code (e.g. `F401`), `message` ruff's message, `fixHint` ruff's fix message when it has one — and merged into the same blocking JSON payload as convention violations. They always block regardless of `--error-on-warnings`, since they're reported as errors.

If `--ruff` is set and no `ruff` executable is found on `PATH` (and at least one proposed write is a `.py` file), that's a verification-unavailable case: fails open with exit `0` and a `konpy gate: warning: ruff not found on PATH (required by --ruff)` line by default, or exits `2` under `--fail-closed`. See [`--fail-closed`](#--fail-closed) above.

### Recursion

`gate` does not spawn a subprocess, so it does not use the `KONPY_HOOK_ACTIVE` recursion sentinel from `konpy hook`. Setting that environment variable does not disable `gate`.

## `hook-propose`

Promotes logged findings — from `konpy review --log` or the deprecated `konpy hook --log`, same `HookFinding` JSONL schema either way — into a reviewable [`ReusableConventionsPackageV1`](./reusable-conventions.md) proposal plus an unmapped report. It never edits `konpy.json`.

```bash
konpy hook-propose
konpy hook-propose .konpy/hook-findings.jsonl
konpy hook-propose findings.jsonl -o packs/ratchet.json --report reports/ratchet-unmapped.md
konpy hook-propose --agent codex --model gpt-5-codex --timeout 600
```

### Argument

| Argument | Default | Description |
| --- | --- | --- |
| `[findings-path]` | `.konpy/hook-findings.jsonl` | JSONL log written by `konpy review --log` or `konpy hook --log` |

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

## `improve`

Runs a read-only agent over one duplicate-function finding from `konpy report`'s duplication lane and asks it for a unified diff plus a short rationale. `konpy improve` never parses, applies, or validates that diff beyond a cheap shape check — it is a proposal tool, not an autofixer. The diff is yours to read, adjust, and apply.

```bash
konpy improve
konpy improve --group calculate_total
konpy improve --agent codex --model gpt-5-codex --output review/proposed.diff
```

### What it selects

1. Runs the same zero-config duplication scan `konpy report` renders (vendor/generated classification included, no `konpy.json` required).
2. Without `--group`, picks the top-ranked duplicate-function group — cross-component duplicates first, then by weighted size (member count x statement count), the same ordering the report shows.
3. With `--group <name>`, picks the group whose canonical function name matches. An unknown name lists the available groups; a name shared by more than one unrelated duplicate cluster is reported as ambiguous (function names are not guaranteed unique across fingerprints) rather than guessed at.
4. No duplicate-function groups in the codebase exits `1` with that message — there's nothing to propose a fix for.

### What it asks the agent to do

The prompt includes the finding (every member's `file:line`, the statement count, a cross-component note when it applies, and the `restrictDuplicateFunctions` fix hint) plus an explicit constraint paragraph:

- work read-only — no file may be edited, created, or deleted;
- verify by reading the actual files, not just the summary, before deciding;
- respect the repository's deployment/isolation model — if the duplicate copies must stay independently deployable (a scaffold/template rendered per project, a vendored snapshot, a separately packaged component), aligning the copies or pushing the fix into the scaffold/template is a valid answer, not extraction into a shared helper;
- the diff must apply cleanly with `patch -p0` from the repository root.

The agent runs with the same read-only CLI flags `konpy hook`/`konpy review` use for their verifier (`--allowedTools Read Grep Glob` for claude, `--sandbox read-only` for codex), so it can read the codebase but never write to it.

### Output

Without `--output`, the agent's response is written verbatim to stdout, so `konpy improve | patch -p0` applies it directly when the diff is good. With `--output <path>`, the response is written to that file instead and stdout just confirms the path. Either way, stderr gets one progress line before the agent starts and one when it finishes; `konpy improve` never touches any other file.

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--group <name>` | string | — | Duplicate-function group to target by canonical function name |
| `--agent <agent>` | `auto` \| `claude` \| `codex` | `auto` | Agent CLI to invoke |
| `--model <model>` | string | `sonnet` | Model passed through to the agent CLI as `--model` |
| `--timeout <seconds>` | float | `300.0` | Timeout for the proposing agent subprocess |
| `-o, --output <path>` | string | — | Write the proposed diff here instead of stdout |
| `--config-path <path>` | string | `konpy.json` (project root) | Only its directory anchors the scan root; the file itself need not exist |

### Exit codes

| Exit | Meaning |
| --- | --- |
| `0` | The agent produced a diff-shaped response |
| `1` | No duplicate-function groups, an unknown/ambiguous `--group`, no supported agent CLI on `PATH`, the agent exited non-zero, or its response wasn't diff-shaped |

A non-diff-shaped response still prints the agent's raw output (to stdout) so you can see what it said, but exits `1` and writes nothing to `--output`.

### Limitation (v1)

`konpy improve` only targets duplicate-function clusters from the report's duplication lane. Repeated-literal groups, unused-code findings, and coverage gaps aren't wired up yet.

## `verify`

Runs the verification-step roster declared in `konpy.json`'s `verify` section: a named list of commands, executed verbatim (no shell), every one of them, every time, in declaration order. It exists so CI, a pre-commit hook, and an agent hook can all call one command instead of each hard-coding its own list of tools.

```bash
konpy verify
konpy verify --config-path path/to/konpy.json
```

### Config shape

```json
{
  "version": "v1",
  "conventions": [],
  "verify": {
    "steps": [
      { "name": "ruff", "run": ["ruff", "check"] },
      { "name": "konpy-check", "run": ["konpy", "check"] },
      { "name": "pytest", "run": ["pytest", "-q"], "timeout": 600 }
    ]
  }
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `steps[].name` | string | — | Unique name for the step, shown in `[verify] <name> ... ok\|FAILED` output. Duplicate names are a config validation error |
| `steps[].run` | list of strings | — | Argv executed verbatim, no shell. `run[0]` is the executable |
| `steps[].timeout` | integer (seconds) | `1800` | How long to let the step run before it's reported as a timeout failure |

### Flags

| Flag | Type | Default | Description |
| --- | --- | --- | --- |
| `--config-path <path>` | string | `konpy.json` (project root) | Path to the config file |

### What it does

1. Loads `konpy.json` exactly like `check`/`explain` do: `extends`, `disable`, `plugins`, `conventionSources` all resolve first, the same as any other command. Placeholders (`--placeholder`, path-captured `{name}`s) are **not** expanded inside `verify` in v1 — `run` argv is used exactly as written in the resolved config.
2. If the resolved config has no `verify` section, prints one pointer message to stderr and exits `1`. It never silently does nothing.
3. Runs every step in declaration order, from the resolved config file's directory — so the roster is repo-root-relative no matter where you invoke `konpy verify` from — with the caller's environment plus `KONPY_VERIFY_ACTIVE=1` (a step can check this to detect it's running under `verify`, the same variable `scripts/verify` itself sets for its own child processes).
4. Every step always runs, even after an earlier one fails: there's no fail-fast short-circuit, so one `konpy verify` run reports everything that's broken, not just the first thing.
5. Streams one line per step as it finishes (`[verify] <name> ... ok (0.42s)` or `[verify] <name> ... FAILED (0.42s)`, with an indented failure message on the line below), then, if anything failed, a final `[verify] FAILED: <name>, <name>, ...` summary naming every failed step.

Each `run[0]` is resolved straight off `PATH`, exactly like any other subprocess call — a repo's own pinned `ruff`/`pytest`/whatever wins over anything `konpy` itself happens to depend on. `konpy verify` never shells out through `sh -c`, so no step argv is ever subject to shell quoting or expansion.

### A missing tool is a failure, not a skip

If a step's executable isn't on `PATH`, that step is reported `FAILED` with an `executable not found: ...` message — the same treatment as a nonzero exit code or a timeout. `konpy verify` never lets "this tool wasn't installed" read as "this check passed": a deterministic gate has to fail loud when it can't actually run, not quietly skip.

### Inheritance

A child config's `verify` section replaces its parent's wholesale under `extends`: the child's `steps` list is used as-is and the parent's is discarded, not merged step-by-step. This is different from `unusedCode`, whose individual fields (`include`, `allow`, `severity`, ...) merge one at a time, with the child overriding only the fields it sets and the parent's other fields surviving. `verify` doesn't merge that way because `VerifyConfigV1` has a single list field (`steps`), and the generic `extends` machinery never merges list values, only replaces them — so a child that wants to keep some of a parent's steps has to repeat them.

### Exit codes

- `0` — every step succeeded.
- `1` — the config is missing or invalid, the resolved config has no `verify` section, or at least one step failed (including a missing executable or a timeout).

### Installing the tools your steps call (`konpy[quality]`)

`konpy verify` doesn't bundle or vendor `ruff`/`basedpyright`/`import-linter` — it just runs whatever `run` names, straight off `PATH`. If your roster calls those three and you don't already have them some other way, the `quality` extra installs them:

```bash
pip install "konpy[quality]"
```

This is purely an installation convenience. A roster that only calls `pytest` and repo-local scripts doesn't need the extra at all, and installing it changes nothing about how `verify` resolves or runs a step.

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

Machine-readable JSON object. It always includes unsuppressed diagnostics, suppressed diagnostics, baselined diagnostics, stale baseline entries, and a summary:

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
  "baselined": [
    {
      "severity": "error",
      "conventionName": "documented-service",
      "filePath": "src/legacy.py",
      "predicateName": "havePairedFile",
      "message": "Missing paired file: tests/test_legacy.py"
    }
  ],
  "baselineStale": [
    {
      "filePath": "src/fixed.py",
      "conventionName": "documented-service",
      "recorded": 2,
      "found": 1
    }
  ],
  "summary": {
    "filesChecked": 6,
    "errors": 1,
    "warnings": 0,
    "suppressed": 1,
    "baselined": 1,
    "durationMs": 10.0
  },
  "truncation": {
    "shown": 2,
    "omitted": 0
  }
}
```

`diagnostics` contains unsuppressed, non-baselined diagnostics only, truncated to `--max-diagnostics`. `suppressed` contains diagnostics suppressed by source comments. `baselined` contains diagnostics demoted by a baseline (see [Baseline and the ratchet](#baseline-and-the-ratchet)) — same element shape as `diagnostics`, never truncated. `baselineStale` lists every `(file, convention)` baseline entry whose recorded count exceeds what's currently found. `severity` is `"error"` or `"warning"`. `line`, `description`, `hint`, `expected`, `found`, and `fixHint` are all omitted (never emitted as `null`) when not applicable to that diagnostic — see [Diagnostic intent and fix direction](#diagnostic-intent-and-fix-direction).

`summary.errors`/`summary.warnings` are always the full pre-truncation totals of `diagnostics` only — baselined violations live solely in `summary.baselined`/`baselined`, never mixed into the error/warning counts. `truncation` is always present: `shown` is `diagnostics.length`, `omitted` is how many unsuppressed, non-baselined diagnostics were cut by `--max-diagnostics` (`0` when nothing was truncated). See [Truncation](#truncation).

`--show-suppressed`/`--show-baselined` do not change JSON output; suppressed and baselined details are always present so machine consumers can audit them.

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

`expected`/`found`/`fix_hint` are populated by the predicates where they can be expressed unambiguously: `exportClasses`, `exportConstants`, `havePairedFile`, `haveDocstrings`, `annotateFunctions`, `restrictAnnotations`, `restrictRepeatedLiterals`, `restrictDuplicateFunctions`, `restrictDecorators`, `restrictBaseClasses`, `restrictCalls`, `restrictImports`, `importFrom`, `importFrom*`/`importTypes*` (current-dir/parents/externals groups), and `matchContent`. Other predicates leave these fields `None` rather than guessing — a vague hint is worse than no hint.

All five fields are additive and optional everywhere they appear: omitted from JSON when absent (never emitted as `null`), and producing no extra line/cell in `default`/`markdown` output when absent. `fix_hint` is data only — konpy never applies it automatically and never emits suppression comments; see [Suppressions](./suppressions.md) for the consent policy on machine-authored changes.

## Truncation

When the number of unsuppressed diagnostics exceeds `--max-diagnostics`, only the first `n` unsuppressed diagnostics are printed and a truncation summary is appended:

```text
... and 437 more diagnostics (use --max-diagnostics to see more)
```

The exit code still reflects all unsuppressed violations — only the printed output is truncated. Suppressed counts are computed from the full run result and are not truncated.

Under `--format json`, the `diagnostics` array is truncated the same way, but `summary.errors`/`summary.warnings` are always the full pre-truncation totals, and a top-level `truncation: {shown, omitted}` key (always present, `omitted: 0` when nothing was cut) makes truncation explicit for machine consumers instead of leaving it to be inferred from `diagnostics.length` — see [`json`](#json).
