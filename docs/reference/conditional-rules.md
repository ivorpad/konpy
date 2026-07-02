# Conditional rules

When a convention's `must` is an **array** of blocks instead of a single object, each block can have its own conditions, scope, and predicates. This unlocks rules like "admin modules must export `admin`" or "test files must import the project's fixtures helper" — structural conventions that linters and the type checker won't catch on their own.

## Object form vs. array form

The object form applies one set of predicates unconditionally to every matched path:

```json
{
  "paths": "packages/{name}",
  "must": {
    "haveType": "directory",
    "haveFiles": ["src/__init__.py"]
  }
}
```

The array form is a list of `MustBlock`s. Each block independently decides whether and how to apply:

```json
{
  "paths": "components/{componentName}",
  "must": [
    { "must": { "haveFiles": ["__init__.py"] } },
    {
      "if": { "hasFile": "tests.py" },
      "for": { "files": "tests.py" },
      "must": { "import": [{ "name": "render", "from": "tests.support" }] }
    },
    {
      "for": { "files": "*_admin.py" },
      "must": { "exportConstants": ["ADMIN"] }
    }
  ]
}
```

Switch from object to array form when you need:
- Different predicates for different files inside the same directory.
- Predicates that apply only when an optional file exists.
- Predicates that apply only to a subset of placeholder values.

## `MustBlock` shape

```json
{
  "name": "test-fixtures-helper",
  "description": "Component test files must use the project's fixtures helper",
  "if": { "hasFile": "tests.py" },
  "for": { "files": "tests.py" },
  "excludeFiles": ["components/legacy/**"],
  "must": { "import": [{ "name": "render", "from": "tests.support" }] },
  "mustNot": { "exportConstants": ["DEBUG"] }
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `must` | `MustPredicates` | yes, unless `mustNot` is present | The predicates this block enforces. See [predicates.md](./predicates.md). |
| `mustNot` | `MustPredicates` | yes, unless `must` is present | The predicates this block forbids. |
| `if` | `{ hasFile }` or `{ placeholderSatisfies }` | no | Gate. Block runs only if the condition holds. |
| `for` | `{ files: string \| string[] }` | no | Scope. Predicates apply to files matching this pattern within the parent path. |
| `excludeFiles` | `string[]` | no | Glob patterns to exclude from the block. |
| `name` | string matching `[a-z0-9-]+` | no | Identifier shown in violation reports. |
| `description` | string | no | Human-readable explanation. |

## `if.hasFile`

Block applies only when the named file exists at (or relative to) the matched path. Templates are resolved using the parent placeholders.

```json
{
  "paths": "components/{componentName}",
  "must": [
    {
      "if": { "hasFile": "tests.py" },
      "for": { "files": "tests.py" },
      "must": { "import": [{ "name": "render", "from": "tests.support" }] }
    }
  ]
}
```

For `components/Button`, the block runs only if `components/Button/tests.py` exists. Components without test files are skipped — no false-positive "missing import" violations.

## `if.placeholderSatisfies`

Block applies only when the named placeholder satisfies a constraint. Syntax, constraint catalog, and examples in [constraints.md](./constraints.md#ifplaceholdersatisfies).

An `if` block has exactly **one** of `hasFile` or `placeholderSatisfies` — not both, not neither.

## `for.files`

Restrict predicates to files matching a sub-pattern within the parent path. The pattern can introduce **new placeholders** that are then available in `must`.

### Single pattern

```json
{
  "paths": "components/{componentName}",
  "must": [
    {
      "for": { "files": "{adminFile}_admin.py" },
      "must": { "exportConstants": ["ADMIN"] }
    }
  ]
}
```

For `components/Button`, the block runs once per `*_admin.py` file inside `Button/`. The new `adminFile` placeholder is available in `must`.

### Multiple patterns

`files` accepts an array of patterns; the union is matched.

```json
{
  "paths": "modules/{moduleName}",
  "must": [
    {
      "for": { "files": ["test_*.py", "*_test.py"] },
      "must": { "import": [{ "name": "make_context", "from": "tests.support" }] }
    }
  ]
}
```

### Combining `if` and `for`

```json
{
  "if": { "hasFile": "tests.py" },
  "for": { "files": "tests.py" },
  "must": { "import": [{ "name": "render", "from": "tests.support" }] }
}
```

`if` gates whether the block runs at all; `for` narrows which files inside the matched path the predicates apply to. Common idiom: gate on the existence of a file, then run predicates only on that file.

## `excludeFiles`

Skip specific files — at the convention level or inside a block.

At the convention level:

```json
{
  "name": "plugin-exports",
  "paths": "plugins/{pluginName}/__init__.py",
  "excludeFiles": ["plugins/storage/__init__.py"],
  "must": {
    "export": ["activate"],
    "exportConstants": ["PLUGIN_ID"]
  }
}
```

Inside a block:

```json
{
  "for": { "files": "*_test.py" },
  "excludeFiles": ["plugins/auth/helpers_test.py"],
  "must": { "import": [{ "name": "make_context", "from": "tests.support" }] }
}
```

For broader, pattern-based exclusion (rather than enumerating exceptions), prefer [path negation](./path-patterns.md#negation) in `paths`.

## Block names

The optional `name` field on a block is shown in violation messages alongside the convention name. Useful when one convention has several blocks:

```json
{
  "name": "component-structure",
  "paths": "components/{componentName}",
  "must": [
    { "must": { "haveFiles": ["__init__.py"] } },
    {
      "name": "test-fixtures-helper",
      "if": { "hasFile": "tests.py" },
      "for": { "files": "tests.py" },
      "must": { "import": [{ "name": "render", "from": "tests.support" }] }
    },
    {
      "name": "admin-export",
      "for": { "files": "*_admin.py" },
      "must": { "exportConstants": ["ADMIN"] }
    }
  ]
}
```

A failure in the `test-fixtures-helper` block reports `[component-structure / test-fixtures-helper]` so the user knows exactly which block fired. Block names match `[a-z0-9-]+`.
