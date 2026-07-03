# konpy

_Enforce consistent code, for agents and humans._

**konpy** is a CLI linter that checks whether files and directories in your **Python** codebase match declared structural conventions — project layout, required files, required module-level definitions/exports/imports, `__init__.py` re-export purity, docstring and annotation coverage, naming patterns, dead code — all declared in a single `konpy.json`. (Distributed on PyPI as **`konpy`**; the import package and CLI are `konpy`.)

_Inspired by [Vercel's konsistent](https://github.com/vercel-labs/konsistent) — reimplemented from scratch for Python._

konpy is deliberately **not** a style linter or type checker. Formatting belongs to ruff, types to mypy. konpy owns the layer above: *"every `src/{name}_service.py` exports a `${name.toPascalCase()}Service` class, has a paired `tests/test_{name}.py`, documents its public API, and never imports from the infrastructure layer."*

## Install & run

```bash
uv tool install --from /path/to/konpy konpy   # or: uv add --dev konpy
konpy            # = konpy check, reads ./konpy.json
konpy validate   # schema-check the config without scanning
konpy check --config-path other.json --max-diagnostics 300
```

## Quickstart

Create `konpy.json` at the repo root:

```json
{
  "$schema": "./konpy.schema.json",
  "version": "v1",
  "conventions": [
    {
      "name": "services-have-shape",
      "description": "Every service module exports its class and has a test.",
      "paths": "src/{name}_service.py",
      "must": {
        "exportClasses": ["${name.toPascalCase()}Service"],
        "havePairedFile": "tests/test_${name}_service.py",
        "haveDocstrings": { "publicOnly": true },
        "annotateFunctions": { "publicOnly": true }
      },
      "mustNot": {
        "matchContent": ["\\bFIXME\\b"],
        "importFrom": "src.infrastructure"
      }
    }
  ]
}
```

`paths` globs capture placeholders (`{name}`) that predicates consume via `${name}` templates with case transforms (`toPascalCase`, `toSnakeCase`, `toConstantCase`, …). Everything under `must` must hold; anything under `mustNot` must not. Full vocabulary: [docs/reference/predicates.md](docs/reference/predicates.md); path grammar: [docs/reference/path-patterns.md](docs/reference/path-patterns.md).

Notable predicates: `haveFiles`, `haveType`, `export*`/`declare*` families, `import`/`importFrom`/`importFromParents`, `areBarrelFiles`, `useDeclarationOrder`, and the coverage/content set: `matchContent` (regex on file content — the escape hatch), `havePairedFile` (repo-root-relative), `haveDocstrings`, `annotateFunctions`. Dead-code detection is configured separately via the top-level `unusedCode` key — next section.

## Unused-code detection

`unusedCode` is a **classifier, not a flagger** — the design goal is zero noise. Instead of reporting every unreferenced name the way `vulture` or basedpyright's `reportUnusedFunction` do, it classifies every definition (module-level functions, classes, and constants, plus one level of class-body methods and attributes) and reports only the two actionable classes, staying silent on the systematic false-positive classes that framework code produces:

```json
{
  "version": "v1",
  "conventions": [],
  "unusedCode": {}
}
```

- **Reported:** `dead` — no reference anywhere (code, tests, entrypoint files, string literals) — and `test-only` — referenced only under `testGlobs`, i.e. code kept alive purely by its own tests, a delete-with-its-tests candidate no comparable tool surfaces.
- **Silent:** decorator-registered handlers (`@app.*`, `@field_validator`, `@pytest.fixture`, …), lifecycle hooks and dunders, model fields on `BaseModel`/`TypedDict`/`Enum`/`@dataclass` classes, and symbols named in entrypoint files (Dockerfile `CMD`, `pyproject.toml`, serverless templates). A bare `{}` already understands pydantic, FastAPI/Flask/Django, pytest, celery, and click/typer via shipped presets.

References are resolved repo-wide, including identifier tokens inside string literals — `"src.lambda_function.handler"` in a Dockerfile keeps `handler` alive. Matching is by bare name and deliberately under-reports before it ever false-positives (see [limitations](docs/reference/unused-code.md#limitations)).

Findings arrive as `warning`-severity diagnostics under the `[unused-code]` label (predicate `unusedCode.dead` / `unusedCode.testOnly` in `--format json`) — gate them in CI with `--error-on-warnings`, and suppress an approved exception with `# konpy: ignore[unused-code]` (the [consent policy](docs/reference/suppressions.md#ai-agents) applies). The config keys (`include`, `testGlobs`, `entrypointFiles`, `registryDecorators`, `hookNames`, `modelBases`) extend the presets; `allow` silences specific names by decision. Because classification needs the whole reference graph, `unusedCode` always scans the entire project — [`--files`/`--changed` scoping](#diff-scoped-checking---files----changed) never narrows or partially runs it. Full taxonomy, presets, and config keys: [docs/reference/unused-code.md](docs/reference/unused-code.md).

## Reusable conventions & the best-practices pack

Rules can be packaged once and consumed everywhere. This repo ships a starter pack at [`packs/python-best-practices.json`](packs/python-best-practices.json):

```json
{
  "version": "v1",
  "conventionSources": { "bp": "./packs/python-best-practices.json" },
  "conventions": [
    "bp/init-files-are-barrels",
    "bp/absolute-imports-only",
    "bp/docstrings-on-public-api",
    "bp/annotated-public-functions",
    { "use": "bp/paired-test-files", "paths": ["src/{name}.py", "!src/__init__.py"] },
    { "use": "bp/class-name-matches-filename", "paths": "src/{name}_service.py" }
  ]
}
```

String form uses the pack rule's own paths; `use` form supplies (or overrides) paths, placeholders, and severity. Authoring guide: [docs/guides/authoring-reusable-conventions.md](docs/guides/authoring-reusable-conventions.md). Copy-paste templates for project-specific rules (layered import bans, DDD layouts, test-suite layout): [docs/guides/templates.md](docs/guides/templates.md).

### More packs: hexagonal architecture and src layout

Two additional off-the-shelf packs live alongside the best-practices one:

- [`packs/hexagonal-architecture.json`](packs/hexagonal-architecture.json) — ports-and-adapters layering: domain modules stay free of adapter/infrastructure imports, ports are `Protocol`/`ABC` boundaries, adapters export an `*Adapter`-suffixed class, and each use case has a paired test. Assumes `src/domain/`, `src/ports/`, `src/adapters/`, `src/use_cases/`.
- [`packs/src-layout.json`](packs/src-layout.json) — `src/` layout hygiene: the project root has `src/` + `pyproject.toml`, every top-level `src/` package has an `__init__.py`, and both flat and one-level-nested modules mirror into `tests/`.

Consume either one the same way, via `conventionSources`:

```json
{
  "version": "v1",
  "conventionSources": {
    "hex": "./packs/hexagonal-architecture.json",
    "layout": "./packs/src-layout.json"
  },
  "conventions": [
    "hex/domain-does-not-import-adapters-or-infrastructure",
    "hex/ports-are-protocols-or-abcs",
    "hex/adapters-export-adapter-suffix",
    "hex/use-cases-paired-with-tests",
    "layout/project-root-uses-src-layout",
    "layout/top-level-src-packages-have-init",
    "layout/top-level-modules-mirror-into-tests",
    "layout/nested-modules-mirror-into-tests"
  ]
}
```

Full per-convention reference, including the layout assumptions each pack makes: [docs/reference/packs.md](docs/reference/packs.md).

### Distributing packs on PyPI

A convention source can be a **bare Python distribution name**. Ship a `konpy.json` (reusable-package format) as package data, publish, and consumers write:

```json
{ "conventionSources": { "acme": "acme-conventions" } }
```

after `uv add --dev acme-conventions`. konpy resolves the installed distribution via `importlib.metadata` — no network at lint time.

## Config inheritance (org base → team → project)

```json
{
  "version": "v1",
  "extends": ["acme-base-config", "./team-overlay.json"],
  "disable": ["legacy-rule"],
  "conventions": [
    { "name": "rule-also-in-base", "paths": "packages/{name}", "must": { "haveFiles": ["README.md", "pyproject.toml"] } }
  ]
}
```

Parents load left-to-right (local paths or installed package names), then the child overlays: `conventions` **concatenate**, a same-`name` convention **replaces** the inherited one in place, `disable` removes inherited rules by name, everything else deep-merges. Cycles are detected and rejected. Details: [docs/reference/configuration.md](docs/reference/configuration.md).

## Custom rules

Three tiers, cheapest first:

1. **`matchContent`** — most "custom rules" are a regex away, no code required:

   ```json
   { "name": "no-naive-utcnow", "paths": "src/**/*.py",
     "mustNot": { "matchContent": ["\\butcnow\\(\\)"] } }
   ```

2. **A reusable pack** — bundle rules built from existing predicates into a `konpy.json` package (local file or PyPI) so every repo consumes the same definitions.

3. **Plugin predicates** — real custom logic as Python code, loaded from entry points. In your plugin package:

   ```toml
   [project.entry-points."konpy.predicates"]
   requireMarker = "acme_konpy.rules:require_marker"
   ```

   ```python
   from konpy.plugin import PredicatePlugin, create_diagnostic

   def check(*, expected, context, structure, convention_name, severity):
       if expected not in context.file_system.read_file(context.path):
           return [create_diagnostic(
               file_path=context.path, predicate_name="requireMarker",
               message=f'Missing marker "{expected}"',
               convention_name=convention_name, severity=severity)]
       return []

   require_marker = PredicatePlugin(
       key="requireMarker", value_model=str, handler=check,
       forbidden_message_template='Forbidden marker "{value}"')
   ```

   Consumers must **opt in explicitly** — konpy never executes code the config didn't name:

   ```json
   { "version": "v1", "plugins": ["acme-konpy"],
     "conventions": [{ "name": "markers", "paths": "src/*.py", "must": { "requireMarker": "PLUGIN_OK" } }] }
   ```

   Plugin keys work under `mustNot` too, get strict value validation from the plugin's own pydantic model, and collide loudly with builtins. Full contract (AST access via `uses_ast`, item-level mustNot, placeholder validation): [docs/reference/plugins.md](docs/reference/plugins.md).

## Using konpy with Claude Code (the agent loop)

konpy was built for exactly one workflow: encode your conventions once in `konpy.json`, then wire them into every stage of a coding agent's loop — before it writes, after each edit, and in CI — so the agent hears one consistent voice everywhere. The pieces below each have their own section; this is the order they compose in:

1. **Bootstrap the rules — don't hand-author them.** Mine an existing codebase with [`konpy infer`](#mining-a-codebase-for-conventions), translate a prose style guide or skill with [`extract-rules`](#extracting-rules-from-skills--style-guides), or start greenfield from the [shipped packs](#reusable-conventions--the-best-practices-pack). All three emit reviewable proposals, never live config.
2. **Prevention: put the rules in the agent's context.** `konpy explain >> CLAUDE.md` renders the resolved config as [agent guidance](#explaining-rules-to-an-agent) — the agent writes conformant code on the first pass instead of getting caught afterwards. Re-run it when the config changes.
3. **Per-edit feedback: a `PostToolUse` hook.** Run [`konpy check --files <edited-file>`](#diff-scoped-checking---files----changed) after every `Edit`/`Write`; on violation the hook exits `2` and the JSON diagnostics land in front of the agent, which fixes them in the same session — with [`expected`/`found`/`fixHint`](#diagnostic-intent-and-fix-direction) so the fix needn't be re-derived from a message string. Recipe: [docs/guides/claude-code-hook.md](docs/guides/claude-code-hook.md). For judgment calls no structural predicate can express, layer the [agentic `konpy hook`](#agentic-verification-hooks) on top (this repo does, via its own `.claude/settings.json`).
4. **Keep exceptions honest.** [Suppressions](#suppressions) require a named rule and a human decision — the consent policy is restated in every `explain` render, so the agent knows it.
5. **Gate and measure.** `konpy check --error-on-warnings` in CI, and the [eval harness](#agent-evaluation) to snapshot violation metrics before/after an agent session and fail on regression.

Division of labor: **ruff owns universal style and correctness; konpy owns *your* architecture** — layout, naming-to-export contracts, import boundaries, paired tests, dead code. They complement, not compete.

### What an agent sees

When the `PostToolUse` hook runs `konpy check --files <edited-file> --format json`, this is the payload that lands in front of the agent. Given a freshly written `src/service.py` that skips docstrings and annotations and leaves a `FIXME` behind — checked against a strict pack of `docstrings-on-public-api`, `annotated-public-functions`, and a `no-fixme` `matchContent` rule — the agent receives:

```json
{
  "diagnostics": [
    {
      "severity": "error",
      "conventionName": "docstrings-on-public-api",
      "filePath": "src/service.py",
      "predicateName": "haveDocstrings",
      "message": "Function \"compute_total\" must have a docstring",
      "line": 1,
      "description": "Public functions must have docstrings.",
      "hint": "Add a one-line docstring describing what the function does.",
      "expected": "docstring on function \"compute_total\"",
      "fixHint": "Add a docstring to function \"compute_total\"."
    },
    {
      "severity": "error",
      "conventionName": "annotated-public-functions",
      "filePath": "src/service.py",
      "predicateName": "annotateFunctions",
      "message": "Function \"compute_total\" must have a return type annotation",
      "line": 1,
      "expected": "return type annotation",
      "fixHint": "Add a return type annotation to function \"compute_total\", e.g. `-> <Type>:`."
    },
    {
      "severity": "error",
      "conventionName": "no-fixme",
      "filePath": "src/service.py",
      "predicateName": "mustNot.matchContent",
      "message": "Forbidden content matching regex \"\\bFIXME\\b\"",
      "line": 2,
      "expected": "\\bFIXME\\b",
      "found": "FIXME",
      "fixHint": "Remove or rewrite the content in src/service.py that matches the pattern `\\bFIXME\\b`."
    }
  ],
  "suppressed": [],
  "summary": { "filesChecked": 1, "errors": 6, "warnings": 0, "suppressed": 0, "durationMs": 0.86 },
  "truncation": { "shown": 6, "omitted": 0 }
}
```

Every diagnostic carries not just a `message` but the machine-actionable `expected`/`found`/`fixHint` and convention-level `description`/`hint` from [Diagnostic intent and fix direction](#diagnostic-intent-and-fix-direction) — so the agent applies the fix directly instead of re-deriving it from prose. (Three of the six errors are shown here for brevity; `summary.errors` is always the full pre-truncation total.) The same run in the default human-readable `--format` — what *you* see at the terminal — renders as:

```
src/service.py
  1  error  Function "compute_total" must have a docstring  [docstrings-on-public-api]
        -> description: Public functions must have docstrings. | hint: Add a one-line docstring describing what the function does. | expected: docstring on function "compute_total" | fix: Add a docstring to function "compute_total".
  1  error  Function "compute_total" must have a return type annotation  [annotated-public-functions]
        -> expected: return type annotation | fix: Add a return type annotation to function "compute_total", e.g. `-> <Type>:`.
  2  error  Forbidden content matching regex "\bFIXME\b"  [no-fixme]
        -> found: FIXME | fix: Remove or rewrite the content in src/service.py that matches the pattern `\bFIXME\b`.

Checked 1 file in 1ms. Found 6 errors.
```

## Extracting rules from skills & style guides

Turn prose best practices — a Claude Code skill's `SKILL.md`, a team style guide, any markdown — into a reviewable pack:

```bash
konpy extract-rules .agents/skills/python-project-structure/SKILL.md
konpy extract-rules style-guide.md -o packs/team-style.json --agent codex --report unmapped.md
```

It shells out to a local agent CLI (`claude -p` or `codex exec`; `--agent auto` is the default and prefers `claude`), pins the agent's model via `--model` (default: `sonnet`, forwarded as the agent CLI's own `--model` flag — pass an explicit value for codex), embeds the predicate vocabulary and pack format in the prompt, and **validates the result against the pack schema before writing anything**. Rules that aren't structurally expressible are never silently dropped — they land in an unmapped-rules report with reasons (that's your ruff/mypy/plugin backlog). The output is a proposal for human review; `extract-rules` never edits `konpy.json`. Guide: [docs/guides/extracting-rules.md](docs/guides/extracting-rules.md).

## Explaining rules to an agent

`konpy explain` renders your fully resolved `konpy.json` (after `extends`/`disable`/`conventionSources`/`plugins`) as concise Markdown or plain-text guidance — one bullet per convention with its name, paths, description, `hint`, and severity — so you can paste it into `CLAUDE.md` and have a code-writing agent follow the rules *before* writing code, not just get caught by `check` afterwards:

```bash
konpy explain > CLAUDE.md
konpy explain --format text
```

It is read-only: no filesystem scan, no diagnostics, no `--fix`. Every render ends with a standing reminder of the [suppression consent policy](docs/reference/suppressions.md#ai-agents) — agents must never add a `# konpy: ignore[...]` comment without explicit human approval.

## Mining a codebase for conventions

`konpy infer` scans an existing codebase for statistical regularities — "94% of modules under `adapters/` export `*Adapter`; here are the 3 violators" — and proposes a reviewable `ReusableConventionsPackageV1`-shaped pack (the same output contract as `extract-rules`: `{"conventionSpecVersion": "v1", "conventions": [...]}`, never a `konpy.json`-shaped document) plus a confidence/violators report, using six deterministic heuristics (no agent call):

```bash
konpy infer > konpy.infer.pack.json
konpy infer --heuristic export-suffix --heuristic paired-test-file -o proposal.json -r report.md
```

The proposed pack goes to stdout (or `--output`); the confidence/violators report goes to stderr (or `--report`). Every proposal is `severity: "warning"` and carries `support`/`total` counts plus a violator list — `infer` never edits `konpy.json` and never reads an existing one. Guide: [docs/guides/inferring-conventions.md](docs/guides/inferring-conventions.md).

## Agentic verification hooks

`konpy hook` wires an agentic verifier into Claude Code's or Codex's `PostToolUse` hooks: after a matched write/edit, it spawns a read-only verifier agent (`claude -p` or `codex exec`) with a natural-language `--prompt` and turns its pass/fail verdict into the hook exit-code contract (0 pass/skip, 2 fail, 1 infra fail-open), with sentinel-based recursion guards so the verifier can't re-trigger the hook that spawned it.

```bash
konpy hook --agent claude --model sonnet --match 'src/**/*.py' --prompt 'Docstrings are not aspirational: verify each function body actually does what its docstring claims.'
```

The verifier's model is pinned via `--model` (default: `sonnet`, forwarded to the agent CLI as its own `--model` flag; set it explicitly for codex). Exit 2 is reserved exclusively for a real fail verdict: every misconfiguration — missing `--prompt`/`--agent`, an invalid `--agent` value, even an option the installed konpy doesn't recognize — fails open with exit 1 rather than surfacing a CLI usage error to the host agent as if it were review feedback.

This is **not** the same mechanism as the [`--files` diff-scoped hook recipe](#diff-scoped-checking---files----changed) below — that one runs `konpy check` directly (deterministic, no LLM call, verifies `konpy.json` structural conventions). `konpy hook` is for checks a structural predicate can't express; use it for the subset of your review that needs judgment, and the deterministic recipe for everything else. This repo dogfoods the agentic hook via its own `.claude/settings.json`. Guide: [docs/guides/hooks.md](docs/guides/hooks.md).

## CLI

| Command | Purpose |
| --- | --- |
| `konpy` / `konpy check` | scan and report violations (exit 1 on errors) |
| `konpy validate` | validate the config only |
| `konpy explain` | render resolved conventions as agent guidance (see above) |
| `konpy extract-rules <src>` | agent-assisted rule extraction (see above) |
| `konpy infer` | mine the codebase for candidate conventions (see above) |
| `konpy hook` | agentic PostToolUse verification hook (see above) |
| `konpy version` | print version |

Useful flags: `--config-path`, `--placeholder name:value`, `--max-diagnostics`, `--format json`, `--show-suppressed`. Full reference: [docs/reference/cli.md](docs/reference/cli.md).

## Diff-scoped checking (`--files` / `--changed`)

Scope a run to files an agent just touched — `konpy check --files src/service.py` or `konpy check --changed` (tracked changes since `HEAD` plus untracked files, per `git diff`/`git ls-files`). `--changed` **requires a git repository**: outside one it prints a single clear message to stderr (not a raw git error dump) and exits `1` — it never silently falls back to a full scan. Scoping is **convention-level**, not file-level: a convention is selected as soon as any file in scope falls in its matched set, and then it's evaluated over its *entire* matched set — so a violation on a sibling file the agent didn't touch can still surface. `havePairedFile` and `unusedCode` are whole-graph predicates; see [Full semantics and edge cases](docs/reference/cli.md#diff-scoped-checking---files----changed) below for exactly how each is handled under scoping.

```bash
konpy check --files src/service.py
konpy check --changed
```

This is what powers the [Claude Code `PostToolUse` hook recipe](docs/guides/claude-code-hook.md): run `konpy check --files <edited-file> --format json` after every `Edit`/`Write` so an agent gets scoped, structured feedback on the file it just changed without waiting for a full check. Full semantics and edge cases: [docs/reference/cli.md#diff-scoped-checking---files----changed](docs/reference/cli.md#diff-scoped-checking---files----changed).

## Diagnostic intent and fix direction

Diagnostics can carry more than a message: an optional convention-level `description`/`hint` (inherited by every diagnostic the convention produces) and predicate-specific `expected`/`found`/`fix_hint` fields, so an agent's next edit doesn't need to be re-derived from a message string.

```json
{
  "name": "documented-service",
  "description": "Service modules must be paired and documented.",
  "hint": "Run the service generator template if you are starting a new service.",
  "paths": "src/service.py",
  "must": { "havePairedFile": "tests/test_service.py" }
}
```

```json
{
  "predicateName": "havePairedFile",
  "message": "Missing paired file: tests/test_service.py",
  "description": "Service modules must be paired and documented.",
  "expected": "tests/test_service.py",
  "fixHint": "Create the paired file at \"tests/test_service.py\"."
}
```

All five fields are optional and additive: omitted from `--format json` when absent (never `null`), and shown as an extra suffix line/cell in `default`/`markdown` output only when populated. `expected`/`found`/`fix_hint` are currently populated by `exportClasses`, `exportConstants`, `havePairedFile`, `haveDocstrings`, `annotateFunctions`, `importFrom`, the `importFrom*`/`importTypes*` group predicates, and `matchContent` — other predicates leave them unset rather than guessing. `fix_hint` is data only; konpy never applies it automatically. Full reference: [docs/reference/cli.md#diagnostic-intent-and-fix-direction](docs/reference/cli.md#diagnostic-intent-and-fix-direction).

## Suppressions

Approved exceptions can be silenced in place, without touching `konpy.json`:

```python
# konpy: ignore-file[max-module-length] -- splitting tracked in TICKET-123
"""Module docstring."""

def orphaned():  # konpy: ignore[docstrings-on-public-api, unused-code] -- approved legacy hook
    ...
```

- **Line-level** `# konpy: ignore[rule-a, rule-b]` on the flagged line (or the line directly above) suppresses those rules' findings anchored to that line.
- **File-level** `# konpy: ignore-file[rule-name]` must appear before the first code line and also covers findings with no line anchor (`matchContent`, `havePairedFile`, `haveType`, `importFrom`).
- The bracketed rule list is **mandatory** — there is no blanket ignore. Names match the `[bracket]` label shown in check output. An optional reason follows ` -- `.

Suppressions are designed to never be invisible:

- Every summary shows the count: `Found 1 error. Suppressed 3 findings.`
- `konpy check --show-suppressed` lists each suppressed finding with its reason; `--format json` always includes the full `suppressed` array.
- Stale or unknown suppressions are themselves reported as warnings (`Unused suppression for "rule-name"`), so dead ignores get cleaned up — and they fail CI under `--error-on-warnings`.
- Suppressed errors don't fail the build; the exit code counts only unsuppressed findings.

**Policy for AI coding agents:** never add a suppression comment without explicit human approval. The correct default is to fix the violation or ask for a decision. When approval is granted, use the narrowest form (line-level over `ignore-file`) and always include the reason. Full grammar and semantics: [docs/reference/suppressions.md](docs/reference/suppressions.md).

## Agent evaluation

`scripts/eval_conventions.py` A/B-compares how much structural drift a coding agent introduces or removes under different guidance strategies, using konpy's own diagnostics as the metric. It runs `konpy check --format json` against a target repo and reduces the result into a stable, diffable metrics summary, so you can snapshot a repo before and after an agent run and diff the two:

```bash
uv run python scripts/eval_conventions.py run /path/to/target-repo --label before --output before.json
# ...agent does its work...
uv run python scripts/eval_conventions.py run /path/to/target-repo --label after --output after.json
uv run python scripts/eval_conventions.py compare before.json after.json
```

The comparison reports files checked, total diagnostics, errors/warnings/suppressed, and per-convention/per-predicate/`unusedCode` breakdowns as `before -> after (delta)`, plus a `PASS`/`FAIL - errors increased` regression check (`compare --fail-on-regression` turns that into a nonzero CI exit code). It is a repo-dev script — stdlib-only, shells out to the `konpy` CLI as a subprocess rather than importing the package — meant for pairing with [`konpy explain`](#explaining-rules-to-an-agent) guidance and the [`--files` hook](#diff-scoped-checking---files----changed) to measure their effect on an agent's output. Guide: [docs/guides/agent-eval.md](docs/guides/agent-eval.md).

## Development

```bash
uv run pytest          # full suite
uv run ruff check .
uv run konpy            # the repo lints itself
uv run python scripts/generate_schema.py   # regenerate konpy.schema.json after schema changes
```

Docs index: [docs/README.md](docs/README.md). The TypeScript original lives in `tmp/konsistent` as a read-only reference; the v1 config grammar is kept compatible (all Python-port additions — `extends`, `disable`, `plugins`, the coverage predicates — are optional keys).
