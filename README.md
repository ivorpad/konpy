# konsistent-py

_Enforce consistent code, for agents and humans._

Python port of [vercel-labs/konsistent](https://github.com/vercel-labs/konsistent) (distributed as **`konsistent-py`**; the import package and CLI are still `konsistent`): a CLI linter that checks whether files and directories in your **Python** codebase match declared structural conventions — project layout, required files, required module-level definitions/exports/imports, `__init__.py` re-export purity, docstring and annotation coverage, naming patterns, dead code — via a declarative `konsistent.json`.

konsistent is deliberately **not** a style linter or type checker. Formatting belongs to ruff, types to mypy. konsistent owns the layer above: *"every `src/{name}_service.py` exports a `${name.toPascalCase()}Service` class, has a paired `tests/test_{name}.py`, documents its public API, and never imports from the infrastructure layer."*

## Install & run

```bash
uv tool install --from /path/to/konsistent-python konsistent-py   # or: uv add --dev konsistent-py
konsistent            # = konsistent check, reads ./konsistent.json
konsistent validate   # schema-check the config without scanning
konsistent check --config-path other.json --max-diagnostics 300
```

## Quickstart

Create `konsistent.json` at the repo root:

```json
{
  "$schema": "./konsistent.schema.json",
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

Notable predicates: `haveFiles`, `haveType`, `export*`/`declare*` families, `import`/`importFrom`/`importFromParents`, `areBarrelFiles`, `useDeclarationOrder`, and the coverage/content set: `matchContent` (regex on file content — the escape hatch), `havePairedFile` (repo-root-relative), `haveDocstrings`, `annotateFunctions`. Dead-code detection is configured separately via the top-level `unusedCode` key ([docs/reference/unused-code.md](docs/reference/unused-code.md)).

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

### Distributing packs on PyPI

A convention source can be a **bare Python distribution name**. Ship a `konsistent.json` (reusable-package format) as package data, publish, and consumers write:

```json
{ "conventionSources": { "acme": "acme-conventions" } }
```

after `uv add --dev acme-conventions`. konsistent resolves the installed distribution via `importlib.metadata` — no network at lint time.

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

2. **A reusable pack** — bundle rules built from existing predicates into a `konsistent.json` package (local file or PyPI) so every repo consumes the same definitions.

3. **Plugin predicates** — real custom logic as Python code, loaded from entry points. In your plugin package:

   ```toml
   [project.entry-points."konsistent.predicates"]
   requireMarker = "acme_konsistent.rules:require_marker"
   ```

   ```python
   from konsistent.plugin import PredicatePlugin, create_diagnostic

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

   Consumers must **opt in explicitly** — konsistent never executes code the config didn't name:

   ```json
   { "version": "v1", "plugins": ["acme-konsistent"],
     "conventions": [{ "name": "markers", "paths": "src/*.py", "must": { "requireMarker": "PLUGIN_OK" } }] }
   ```

   Plugin keys work under `mustNot` too, get strict value validation from the plugin's own pydantic model, and collide loudly with builtins. Full contract (AST access via `uses_ast`, item-level mustNot, placeholder validation): [docs/reference/plugins.md](docs/reference/plugins.md).

## Extracting rules from skills & style guides

Turn prose best practices — a Claude Code skill's `SKILL.md`, a team style guide, any markdown — into a reviewable pack:

```bash
konsistent extract-rules .agents/skills/python-project-structure/SKILL.md
konsistent extract-rules style-guide.md -o packs/team-style.json --agent codex --report unmapped.md
```

It shells out to a local agent CLI (`claude -p` or `codex exec`; `--agent auto` is the default and prefers `claude`), embeds the predicate vocabulary and pack format in the prompt, and **validates the result against the pack schema before writing anything**. Rules that aren't structurally expressible are never silently dropped — they land in an unmapped-rules report with reasons (that's your ruff/mypy/plugin backlog). The output is a proposal for human review; `extract-rules` never edits `konsistent.json`. Guide: [docs/guides/extracting-rules.md](docs/guides/extracting-rules.md).

## Explaining rules to an agent

`konsistent explain` renders your fully resolved `konsistent.json` (after `extends`/`disable`/`conventionSources`/`plugins`) as concise Markdown or plain-text guidance — one bullet per convention with its name, paths, description, `hint`, and severity — so you can paste it into `CLAUDE.md` and have a code-writing agent follow the rules *before* writing code, not just get caught by `check` afterwards:

```bash
konsistent explain > CLAUDE.md
konsistent explain --format text
```

It is read-only: no filesystem scan, no diagnostics, no `--fix`. Every render ends with a standing reminder of the [suppression consent policy](docs/reference/suppressions.md#ai-agents) — agents must never add a `# konsistent: ignore[...]` comment without explicit human approval.

## CLI

| Command | Purpose |
| --- | --- |
| `konsistent` / `konsistent check` | scan and report violations (exit 1 on errors) |
| `konsistent validate` | validate the config only |
| `konsistent explain` | render resolved conventions as agent guidance (see above) |
| `konsistent extract-rules <src>` | agent-assisted rule extraction (see above) |
| `konsistent version` | print version |

Useful flags: `--config-path`, `--placeholder name:value`, `--max-diagnostics`, `--format json`, `--show-suppressed`. Full reference: [docs/reference/cli.md](docs/reference/cli.md).

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

All five fields are optional and additive: omitted from `--format json` when absent (never `null`), and shown as an extra suffix line/cell in `default`/`markdown` output only when populated. `expected`/`found`/`fix_hint` are currently populated by `exportClasses`, `exportConstants`, `havePairedFile`, `haveDocstrings`, `annotateFunctions`, `importFrom`, the `importFrom*`/`importTypes*` group predicates, and `matchContent` — other predicates leave them unset rather than guessing. `fix_hint` is data only; konsistent never applies it automatically. Full reference: [docs/reference/cli.md#diagnostic-intent-and-fix-direction](docs/reference/cli.md#diagnostic-intent-and-fix-direction).

## Suppressions

Approved exceptions can be silenced in place, without touching `konsistent.json`:

```python
# konsistent: ignore-file[max-module-length] -- splitting tracked in TICKET-123
"""Module docstring."""

def orphaned():  # konsistent: ignore[docstrings-on-public-api, unused-code] -- approved legacy hook
    ...
```

- **Line-level** `# konsistent: ignore[rule-a, rule-b]` on the flagged line (or the line directly above) suppresses those rules' findings anchored to that line.
- **File-level** `# konsistent: ignore-file[rule-name]` must appear before the first code line and also covers findings with no line anchor (`matchContent`, `havePairedFile`, `haveType`, `importFrom`).
- The bracketed rule list is **mandatory** — there is no blanket ignore. Names match the `[bracket]` label shown in check output. An optional reason follows ` -- `.

Suppressions are designed to never be invisible:

- Every summary shows the count: `Found 1 error. Suppressed 3 findings.`
- `konsistent check --show-suppressed` lists each suppressed finding with its reason; `--format json` always includes the full `suppressed` array.
- Stale or unknown suppressions are themselves reported as warnings (`Unused suppression for "rule-name"`), so dead ignores get cleaned up — and they fail CI under `--error-on-warnings`.
- Suppressed errors don't fail the build; the exit code counts only unsuppressed findings.

**Policy for AI coding agents:** never add a suppression comment without explicit human approval. The correct default is to fix the violation or ask for a decision. When approval is granted, use the narrowest form (line-level over `ignore-file`) and always include the reason. Full grammar and semantics: [docs/reference/suppressions.md](docs/reference/suppressions.md).

## Development

```bash
uv run pytest          # full suite
uv run ruff check .
uv run konsistent      # the repo lints itself
uv run python scripts/generate_schema.py   # regenerate konsistent.schema.json after schema changes
```

Docs index: [docs/README.md](docs/README.md). The TypeScript original lives in `tmp/konsistent` as a read-only reference; the v1 config grammar is kept compatible (all Python-port additions — `extends`, `disable`, `plugins`, the coverage predicates — are optional keys).
