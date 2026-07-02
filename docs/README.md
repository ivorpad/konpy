# konsistent documentation

`konsistent` is a CLI linter that checks whether files and directories in your Python codebase match declared structural patterns. It fills a gap that Ruff, Flake8, and Pylint don't cover: they enforce code style and best practices within files, but none of them verify project-level structural conventions — like "every provider package must export the same shape" or "every adapter must extend the base class."

This is the Python port of [vercel-labs/konsistent](https://github.com/vercel-labs/konsistent); it keeps the `konsistent.json` v1 grammar but analyzes Python source via the standard-library `ast` module instead of TypeScript.

## Where to start

- **New here?** [Getting started](./guides/getting-started.md) — install, write your first config, run the CLI.
- **Inheriting a codebase?** [Exploring codebases](./guides/exploring-codebases.md) — how to identify patterns worth enforcing before writing rules.
- **Have violations?** [Fixing violations](./guides/fixing-violations.md) — workflow for triaging and resolving them.

## Guides

- [Getting started](./guides/getting-started.md) — install, write a config, run the CLI.
- [Examples](./guides/examples.md) — common patterns library.
- [Templates](./guides/templates.md) — copy-paste project-specific convention templates.
- [Exploring codebases](./guides/exploring-codebases.md) — what to look for before writing rules.
- [Fixing violations](./guides/fixing-violations.md) — triage workflow.
- [CI integration](./guides/ci-integration.md) — GitHub Actions, output formats, PR comments.
- [Authoring reusable conventions](./guides/authoring-reusable-conventions.md) — publish a convention package others can consume.
- [Extracting rules](./guides/extracting-rules.md) — use an explicit local agent command to draft reusable conventions from prose.
- [Inferring conventions](./guides/inferring-conventions.md) — mine an existing codebase for candidate conventions with `konsistent infer`.
- [Claude Code hook integration](./guides/claude-code-hook.md) — run `konsistent check --files` automatically after Claude edits a file.
- [Agent evaluation](./guides/agent-eval.md) — A/B-compare agent runs using konsistent's own diagnostics as the metric.

## Reference

- [CLI](./reference/cli.md) — commands, flags, output formats, exit codes, [diagnostic intent and fix direction](./reference/cli.md#diagnostic-intent-and-fix-direction) (`description`, `hint`, `expected`, `found`, `fix_hint`), and [`konsistent explain`](./reference/cli.md#explain) — render the resolved config as prevention-side agent guidance for a `CLAUDE.md`.
- [konsistent.json configuration](./reference/configuration.md) — top-level schema, convention shape, and the optional [`hint`](./reference/configuration.md#hint) field.
- [Path patterns](./reference/path-patterns.md) — globs, placeholders, case transformations, negation.
- [Predicates](./reference/predicates.md) — every built-in `must` predicate and how `mustNot` works.
- [Plugins](./reference/plugins.md) — custom predicate entry points, descriptor API, opt-in loading, and runtime validation.
- [Constraints](./reference/constraints.md) — `matches`, `segments` for filtering placeholders.
- [Conditional rules](./reference/conditional-rules.md) — `if`, `for`, `excludeFiles` blocks inside `must` arrays.
- [Case maps](./reference/case-maps.md) — `kebabToPascalMap`, `kebabToCamelMap` for acronyms and special casing.
- [Reusable conventions](./reference/reusable-conventions.md) — `conventionSources`, string and `use` references, merge semantics, error reference.
- [Reusable packs](./reference/packs.md) — per-convention reference for the shipped packs (`python-best-practices.json`, `hexagonal-architecture.json`, `src-layout.json`), including each pack's layout assumptions and hints.
- [Unused-code detection](./reference/unused-code.md) — the optional `unusedCode` classifier: taxonomy, config keys, framework presets, limitations.
- [Suppressions](./reference/suppressions.md) — inline `# konsistent: ignore[...]` comments for approved exceptions, visibility guarantees, and the rules AI agents must follow.

## Reusable packs

The repo includes reusable convention packs under [`../packs/`](../packs/):

- [`python-best-practices.json`](../packs/python-best-practices.json) — general Python structural conventions: barrel `__init__.py` files, absolute imports, docstrings, annotations, paired tests, `__all__` discipline, TODO hygiene, README-per-component.
- [`hexagonal-architecture.json`](../packs/hexagonal-architecture.json) — ports-and-adapters layering: domain purity (no adapter/infrastructure imports), Protocol/ABC ports, `*Adapter`-suffixed adapter exports, use-case/test pairing. Assumes a single-package `src/domain/`, `src/ports/`, `src/adapters/`, `src/use_cases/` layout.
- [`src-layout.json`](../packs/src-layout.json) — `src/` layout conventions and tests mirroring, both flat (`src/<module>.py` → `tests/test_<module>.py`) and one level nested (`src/<package>/<module>.py` → `tests/<package>/test_<module>.py`).

Full per-convention reference for all three: [Reusable packs](./reference/packs.md).

## Schema

The machine-readable schema ships in the repo as `konsistent.schema.json`. Reference it from your `konsistent.json` for editor autocomplete:

```json
{
  "$schema": "./konsistent.schema.json",
  "version": "v1",
  "conventions": []
}
```

The schema includes built-in config keys such as `plugins`, but plugin predicate keys are validated dynamically by `konsistent validate` / `konsistent check` after the configured plugin distributions are loaded.
