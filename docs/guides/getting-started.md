# Getting started

This guide takes you from zero to a working `konsistent.json` in a few minutes.

## 1. Install

```bash
uv add --dev konsistent      # add to a uv project
# or
pip install konsistent       # install with pip
```

You can then run it with `uv run konsistent`, or `uvx konsistent` to run without installing it into the project.

## 2. Create `konsistent.json`

Create `konsistent.json` at the project root with at least the `version` field and one convention. The simplest possible config has a single rule:

```json
{
  "$schema": "./konsistent.schema.json",
  "version": "v1",
  "conventions": [
    {
      "paths": "packages/{name}",
      "must": {
        "haveType": "directory",
        "haveFiles": ["src/__init__.py"]
      }
    }
  ]
}
```

This says: every `packages/<name>` is a directory and must contain `src/__init__.py`.

The `$schema` line gives you autocomplete in editors that respect the JSON schema reference (VS Code, JetBrains, …). The schema ships in the repo as `konsistent.schema.json`.

## 3. Run the CLI

```bash
uv run konsistent
```

When everything passes:

```
Checked 6 files in 8ms. No violations found.
```

When violations are found:

```
packages/anthropic
  -  error  Missing required file "src/__init__.py"  [must-have-files]

Checked 6 files in 10ms. Found 1 error.
```

## 4. Add more conventions

Most useful conventions involve **placeholders** — captured parts of the path you can reference inside `must`. For example, every package barrel must export a name matching the package:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "package-barrels",
      "paths": "packages/{packageName}/src/__init__.py",
      "must": {
        "export": ["${packageName}"]
      }
    }
  ]
}
```

For `packages/anthropic/src/__init__.py`, the rule requires the module to expose the public name `anthropic`. See [path-patterns.md](../reference/path-patterns.md) for the full placeholder syntax (case transformations, regex extraction, constraints).

## 5. Check the schema

After every edit, validate the config:

```bash
uv run konsistent validate
```

The validator catches schema errors (typos, wrong types, unknown fields). If validation passes, run `uv run konsistent` to apply the rules to the codebase.

## What to put in your config

If you're inheriting an existing codebase, don't write rules from scratch — explore the codebase first to identify the patterns that already exist. See [exploring-codebases.md](./exploring-codebases.md) for the systematic approach.

For inspiration, browse [examples.md](./examples.md) for a library of common patterns (provider packages, factory functions, adapter classes, conditional rules, …).

## What to do about violations

If `konsistent` reports many violations across the same rule, the rule itself may be wrong — the codebase may not have actually adopted that convention. See [fixing-violations.md](./fixing-violations.md) for the workflow that distinguishes "the rule is wrong" from "the code is wrong" and walks through fixing each.

## Next steps

- [konsistent.json reference](../reference/configuration.md) — full top-level shape and convention fields.
- [Predicates](../reference/predicates.md) — every `must` predicate with examples.
- [CI integration](./ci-integration.md) — wire `konsistent` into GitHub Actions.
