# Authoring reusable conventions

This guide walks you through writing a package of reusable conventions that other configs can consume by name via a local JSON file or an installed Python distribution.

For the consumer-facing reference (how a `konpy.json` declares `conventionSources` and references your conventions), see [reusable-conventions.md](../reference/reusable-conventions.md).

> **Scope of the Python port.** Convention packages are plain JSON files consumed via a **local path** or as package data in an **installed Python distribution**. There is no `emit` build CLI. You author the JSON directly.

## What you ship

A reusable-conventions package is a single JSON file with a `conventionSpecVersion: "v1"` literal and a `conventions: ReusableConvention[]` array:

```json
{
  "conventionSpecVersion": "v1",
  "conventions": [
    {
      "name": "package-dir-must-have-readme-file",
      "description": "Every package directory under packages/ must contain a README.md file.",
      "paths": ["packages/*"],
      "must": {
        "haveFiles": ["README.md"]
      }
    }
  ]
}
```

`conventionSpecVersion: "v1"` pins the spec your conventions target — future versions can change the format and consumers will be told to upgrade `konpy`.

This format is for `conventionSources`. Package-backed `extends` files are different: they are full `konpy.json` configs with `"version": "v1"`.

## Convention shape

A reusable convention has the same fields as a hand-written one with three adjustments:

- `name` and `description` are **required** (consumers see them in error messages and source listings). `description` is also surfaced automatically on every diagnostic the convention produces.
- `hint` is **optional** — a consumer-facing nudge for fixing violations, surfaced on diagnostics alongside `description`. See [configuration.md#hint](../reference/configuration.md#hint).
- `must` and `mustNot` must use the **flat object form** (`MustPredicates`). The `MustBlock[]` form is not allowed in reusable conventions — see [Restrictions](../reference/reusable-conventions.md#restrictions).
- `paths` is **optional**. Omit it to force consumers to supply `paths` at the use-site (useful when the right pattern depends on the consuming project's layout). When `paths` is omitted, consumers can only reference the convention via the `use` form.

## Consume from a config

Drop the JSON file somewhere in (or alongside) the consuming project, then bind it to a vendor prefix in the consumer's `konpy.json`:

```json
{
  "$schema": "./konpy.schema.json",
  "version": "v1",
  "conventionSources": {
    "myteam": "./conventions/myteam.json"
  },
  "conventions": [
    "myteam/package-dir-must-have-readme-file"
  ]
}
```

The path is resolved against the config file's directory. Run `uv run konpy check` in the consumer; the convention runs as if it had been written inline.

For a convention without `paths`, the consumer must use the `use` form and supply `paths`:

```json
{
  "use": "myteam/module-must-export-equivalent-function",
  "paths": ["src/commands/{commandName}.py"]
}
```

## Ship as an installed Python distribution

You can also ship reusable conventions as package data in a Python distribution. Consumers reference the installed distribution name directly:

```json
{
  "version": "v1",
  "conventionSources": {
    "myteam": "acme-konpy-conventions"
  },
  "conventions": [
    "myteam/package-dir-must-have-readme-file"
  ]
}
```

`konpy` resolves a bare distribution name using Python packaging metadata and looks for `konpy.json` in this order:

1. `<top-level import package>/konpy.json`
2. a `konpy.json` file listed among the distribution's `.dist-info` files

A typical distribution layout is:

```text
acme-konpy-conventions/
  pyproject.toml
  src/
    acme_konpy_conventions/
      __init__.py
      konpy.json
```

With Hatchling, include the JSON as package data:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/acme_konpy_conventions"]
artifacts = ["src/acme_konpy_conventions/konpy.json"]
```

The exact packaging configuration depends on your build backend; the important part is that the installed distribution includes `konpy.json` either at the top-level import package root or as a listed distribution file.

Package names must be valid Python distribution names matching `[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]`. npm-style specifiers such as `@scope/pkg` and subpaths such as `pkg/subpath` are invalid.

`--config-package` is unrelated: it remains unsupported. Installed package support applies to values inside `conventionSources` and `extends` in a local config.

## What to put in your conventions

A reusable convention is most useful when it captures a structural rule that's specific to a library or organization but agnostic to the consuming project's layout. Two patterns work well:

- **Self-contained** — the convention declares its own `paths` (e.g. `packages/*` for any project that uses a `packages/` layout). Consumers reference it as a string.
- **Use-site paths** — the convention omits `paths` and parameterizes via placeholders that the consumer's `paths` declares (e.g. `must.exportFunctions: [{ name: "${commandName}" }]` with no `paths` at all). Consumers must use the `use` form and supply `paths` like `["src/commands/{commandName}.py"]`.

A single file can ship both kinds.

## Versioning

`conventionSpecVersion: "v1"` is the spec version. It only changes if `konpy` itself ships a new convention spec; existing v1 packages keep working when consumers upgrade `konpy` minor versions.

If you publish conventions as a Python distribution, use normal Python package versioning for releases. Consumers control which convention version is installed in their project environment.

## See also

- [Reusable conventions reference](../reference/reusable-conventions.md) — the consumer side.
- [konpy.json reference](../reference/configuration.md) — surrounding config shape.
- [Predicates](../reference/predicates.md) — what you can express inside `must`.
