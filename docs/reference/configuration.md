# konsistent.json

The `konsistent.json` file declares the structural conventions the CLI enforces. By default it lives at the project root; use `--config-path` to put it elsewhere. (The `--config-package` flag exists for upstream compatibility but always errors as unsupported in the Python port — see [cli.md](./cli.md#flags).)

## Top-level shape

```json
{
  "$schema": "./konsistent.schema.json",
  "version": "v1",
  "plugins": ["acme-konsistent-rules"],
  "kebabToPascalMap": { "openai": "OpenAI" },
  "kebabToCamelMap": { "openai": "openAI" },
  "conventions": [
    {
      "name": "provider-packages",
      "paths": "packages/{providerId}",
      "must": {
        "haveType": "directory",
        "haveFiles": ["src/__init__.py"]
      }
    }
  ]
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | `"v1"` | yes | Configuration version. Currently always `"v1"`. |
| `$schema` | string | no | Path to `konsistent.schema.json` for editor autocomplete. |
| `extends` | `string[]` | no | Load and merge parent `konsistent.json` files before this config. Local paths resolve relative to the config file that declares them. Bare Python distribution names resolve installed package configs. |
| `disable` | `string[]` | no | Remove inherited named conventions by raw top-level convention `name`. Applies only during inheritance and is not present at runtime. |
| `plugins` | `string[]` | no | Explicitly opt into installed Python distributions that expose plugin predicates through `konsistent.predicates` entry points. See [plugins.md](./plugins.md). |
| `conventions` | `Convention[]` | yes | Array of convention rules (see below). Each entry can be a hand-written convention, a string reference, or a `use` reference — see [reusable-conventions.md](./reusable-conventions.md). |
| `conventionSources` | `Record<string, string>` | no | Vendor-prefix bindings for local reusable-convention JSON files or installed Python distribution convention packages. See [reusable-conventions.md](./reusable-conventions.md). |
| `kebabToPascalMap` | `Record<string, string>` | no | Override default kebab → PascalCase conversion. See [case-maps.md](./case-maps.md). |
| `kebabToCamelMap` | `Record<string, string>` | no | Override default kebab → camelCase conversion. See [case-maps.md](./case-maps.md). |

## Plugins

`plugins` enables custom predicate keys from installed Python distributions:

```json
{
  "version": "v1",
  "plugins": ["acme-konsistent-rules"],
  "conventions": [
    {
      "name": "acme-marker",
      "paths": "src/*.py",
      "must": {
        "acmeMarker": "ACME_OK"
      }
    }
  ]
}
```

Plugins are explicit opt-in only. `konsistent` never auto-discovers entry points from installed packages that are not named in `plugins`.

Each listed distribution is resolved through Python package metadata and filtered to entry points in the `konsistent.predicates` group. Plugin predicate keys are then accepted in `must` and `mustNot` only for that config load.

The checked-in JSON Schema can expose the top-level `plugins` field, but it cannot statically enumerate arbitrary plugin predicate keys. Use `konsistent validate` to runtime-validate plugin keys and plugin value models.

See [plugins.md](./plugins.md) for plugin authoring, entry-point rules, collision errors, `mustNot`, and placeholder validation.

## Config inheritance

Use `extends` to build project variants from shared base configs:

```json
{
  "version": "v1",
  "extends": ["./shared/base-konsistent.json"],
  "disable": ["legacy-package-license"],
  "conventions": [
    {
      "name": "package-shape",
      "paths": "packages/{packageName}",
      "must": {
        "haveFiles": ["README.md", "pyproject.toml"]
      }
    }
  ]
}
```

Each `extends` entry loads a full `konsistent.json` using the same path classification as `conventionSources`:

| Value shape | Interpretation |
| --- | --- |
| Starts with `.` or is absolute | Relative or absolute path to another config file. Relative paths resolve against the config file that declares the `extends` entry. |
| Bare Python distribution name | Installed distribution lookup. `konsistent` looks for `<top-level import package>/konsistent.json`, then for a `konsistent.json` file listed among the distribution's `.dist-info` files. |
| Contains `/` or npm-style `@scope/pkg` syntax | Invalid Python distribution name. Use a local path or a valid installed Python distribution name. |

Installed distribution names must match `[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]`.

A package-loaded `extends` file must be a full raw config:

```json
{
  "version": "v1",
  "conventions": []
}
```

This is intentionally different from `conventionSources` package data, which must be a reusable-conventions package using `conventionSpecVersion: "v1"` — see [reusable-conventions.md](./reusable-conventions.md#conventionsources).

Parents may themselves have `extends`. Cycles are rejected before any scan runs.

Parents may also declare `plugins`. Plugin lists merge parent-first, then child, with duplicates removed by normalized distribution name. This lets inherited conventions depend on plugin predicates without requiring every child config to repeat the same plugin list.

### Merge order

Configs merge as raw JSON before reusable-convention expansion, CLI placeholders, and placeholder validation:

1. Parent configs merge left-to-right.
2. The child config overlays the merged parents.
3. `extends` and `disable` are stripped from the final runtime config.

For most top-level fields, merge uses the same deep-merge semantics as reusable convention overrides:

| Field kind | Rule |
| --- | --- |
| Plain object, such as `kebabToPascalMap`, `kebabToCamelMap`, `conventionSources`, or `unusedCode` | Recursive deep-merge. |
| Array | Later array replaces earlier array. |
| Scalar | Later value replaces earlier value. |

`plugins` is the exception to array replacement: parent plugins and child plugins are union-concatenated, preserving first occurrence order after normalizing distribution names.

```json
// parent
{ "plugins": ["acme-base-rules"] }

// child
{ "plugins": ["team-rules"] }

// merged
{ "plugins": ["acme-base-rules", "team-rules"] }
```

### Convention merge

`conventions` has inheritance-specific semantics:

- Parent conventions come first.
- Child conventions come last.
- A later raw convention object with the same top-level `name` replaces the earlier convention in place.
- Anonymous conventions append.
- String references append.
- `{ "use": ... }` references append because they do not have a raw top-level `name`.

Replacement happens before reusable-reference expansion. That means replacement only sees names written directly on raw convention objects; it does not inspect names exported by reusable convention packages.

### Disable inherited conventions

`disable` removes inherited conventions by raw top-level `name`:

```json
{
  "version": "v1",
  "extends": ["./shared/base-konsistent.json"],
  "disable": ["package-must-have-license"],
  "conventions": []
}
```

Rules:

- `disable` only removes conventions inherited from ancestors.
- It does not remove conventions declared in the same config file.
- Disabling a missing name is a no-op.
- It cannot remove anonymous conventions, string references, or `{ "use": ... }` references because inheritance merges raw config before reusable-reference expansion.
- If a config disables `"x"` and also declares its own convention named `"x"`, the local convention remains.

### Relative paths in inherited configs

Relative paths inside a local parent config stay relative to that parent file.

For inherited local `conventionSources`, konsistent rewrites local relative source paths to absolute paths during raw inheritance loading. This makes the final merged config resolve reusable convention files from the directory where they were declared, not from the child config's directory.

The root config's own `conventionSources` keep the existing behavior and resolve relative to the root config file's directory.

Package-loaded configs do not have a filesystem directory. Inside a package-loaded config:

- bare Python distribution names in `extends` and `conventionSources` are allowed;
- absolute local paths are allowed;
- relative local-path `extends` entries are rejected;
- relative local-path `conventionSources` entries are rejected.

Use another installed distribution name when one package config needs to depend on another package-shipped config or convention source.

### Inheritance errors

All inheritance errors are surfaced by the CLI before any scanning starts.

| Condition | Error string |
| --- | --- |
| Empty `extends` entry | `Config extends entry in <including_config_path> has empty value.` |
| Invalid package `extends` name | `Config extends "<value>" from <including_path>: invalid Python distribution name. Bare package sources must match [A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9].` |
| Package `extends` distribution not installed | `Config extends "<value>" from <including_path>: installed Python distribution not found. Install it or use a local path in extends.` |
| Package `extends` distribution has no `konsistent.json` | `Config extends "<value>" from <including_path>: installed Python distribution does not contain konsistent.json. Looked for <top-level import package>/konsistent.json and a distribution file named konsistent.json.` |
| Relative local-path `extends` inside package-loaded config | `Config extends "<value>" from <including_path>: relative local-path extends are not supported inside package-loaded configs. Use an absolute path or an installed package name.` |
| Relative `conventionSources` inside package-loaded config | `Config extends "<package_value>" from <including_path>: package config at <location> declares relative conventionSources["<prefix>"] = "<source_value>". Relative conventionSources are not supported inside package-loaded configs; use an absolute path or an installed package name.` |
| Unreadable parent config | `Config extends "<value>" from <including_path>: could not read file at <resolved_path>.` |
| Malformed parent JSON | `Config extends "<value>" from <including_path>: malformed JSON at <location>.` |
| Invalid parent config schema | `Config extends "<value>" from <including_path>: invalid config at <location>:` followed by validation issues. |
| Cycle | `Config inheritance cycle detected: <path-or-package-a> -> <path-or-package-b> -> <path-or-package-a>.` |

## Conventions

A convention is a rule that says "files matching `paths` must satisfy `must` and must not satisfy `mustNot`."

```json
{
  "name": "provider-barrels",
  "description": "Each provider package __init__ must re-export the provider object",
  "severity": "error",
  "paths": "packages/{providerId}/src/__init__.py",
  "must": {
    "export": ["${providerId}"]
  }
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `paths` | `string` or `string[]` | yes | Glob pattern(s) with `{placeholder}` extraction. See [path-patterns.md](./path-patterns.md). |
| `must` | `MustPredicates` or `MustBlock[]` | yes, unless `mustNot` is present | The conditions that matched paths must satisfy. See [predicates.md](./predicates.md) and [conditional-rules.md](./conditional-rules.md). |
| `mustNot` | `MustPredicates` | yes, unless `must` is present | The conditions that matched paths must not satisfy. Unlike `must`, this only accepts the object form. |
| `name` | string matching `[a-z0-9-]+` | no | Identifier shown in violation reports. |
| `description` | string | no | Human-readable explanation. |
| `severity` | `"error"` \| `"warning"` | no, default `"error"` | See [Severity](#severity). |
| `excludeFiles` | `string[]` | no | Glob patterns to exclude from the matched paths. |
| `placeholders` | `Record<string, string>` | no | Static placeholder values for names that are not captured from `paths`. See [Static placeholder values](./path-patterns.md#static-placeholder-values). |

The configuration is `strict` — unknown fields cause a validation error. Run `konsistent validate` to catch typos.

## `must`: predicates or blocks

`must` accepts two shapes.

### Object form (single predicate group)

```json
"must": {
  "haveType": "directory",
  "haveFiles": ["__init__.py"],
  "export": ["create_service"]
}
```

All listed predicates apply unconditionally to every matched path. See [predicates.md](./predicates.md) for the full catalog. Plugin predicates may also appear here when their distribution is listed in top-level `plugins`.

### Array form (multiple blocks with conditions)

```json
"must": [
  { "must": { "haveFiles": ["__init__.py"] } },
  {
    "if": { "hasFile": "tests.py" },
    "for": { "files": "tests.py" },
    "must": { "import": [{ "name": "make_context", "from": "tests.support" }] }
  }
]
```

Each entry is a `MustBlock` that can have `if`, `for`, `excludeFiles`, `name`, and `description`. See [conditional-rules.md](./conditional-rules.md). An entry may alternatively be a reusable-convention reference of the form `{ "use": "<vendor>/<name>", ...overrides }`, which expands into a `MustBlock` — see [reusable-conventions.md](./reusable-conventions.md#use-inside-a-parents-must).

## `mustNot`: negated predicates

`mustNot` accepts the same predicate object shape as object-form `must`, but reverses the result. For example, this fails when a matched file exports `DEBUG`:

```json
"mustNot": {
  "exportConstants": ["DEBUG"]
}
```

`mustNot` is only object-form. It cannot contain a `MustBlock[]`, string references, or `{ "use": ... }` references. Use it inside a `must` block when you need `if`, `for`, or `excludeFiles` scoping.

Plugin predicates also participate in `mustNot` when their descriptor provides a forbidden-message template — see [plugins.md](./plugins.md#mustnot).

## Severity

By default, convention violations are errors and produce a non-zero exit code. Mark a convention as a warning with `"severity": "warning"`:

```json
{
  "paths": "packages/{name}/src/__init__.py",
  "severity": "warning",
  "must": {
    "exportTypes": ["${name.toPascalCase()}Config"]
  }
}
```

Warnings are displayed in yellow and do not cause a non-zero exit code. The CLI flags [`--error-on-warnings` and `--diagnostic-level`](./cli.md#flags) change how warnings affect the exit code and whether warning-severity conventions are evaluated at all.

## `excludeFiles`

Skip specific files from a convention without changing the path pattern:

```json
{
  "paths": "src/**/*.py",
  "excludeFiles": ["**/test_*.py", "src/internal/**"],
  "must": {
    "export": ["main"]
  }
}
```

`excludeFiles` accepts the same glob syntax as `paths` (without placeholder extraction). Path negation in `paths` (`"!path"`) is the inverse — see [path-patterns.md](./path-patterns.md#negation).

## Validation

Run [`konsistent validate`](./cli.md#validate) after every edit to catch schema errors. The schema ships in the repo as `konsistent.schema.json`.

For plugin predicates, the static JSON Schema can validate `plugins` itself but cannot enumerate plugin-provided predicate keys. `konsistent validate` loads the configured plugin descriptors and performs plugin-aware runtime validation.
