# Examples

A library of common patterns you can copy into your `konpy.json`. Each example is a complete, valid convention — drop it in and adjust the path and names.

For deeper coverage of any concept, follow the cross-links to the reference docs.

## Provider packages

Every `packages/{providerId}` is a directory with a barrel `__init__.py` and a provider implementation module.

```json
{
  "name": "provider-packages",
  "paths": "packages/{providerId}",
  "must": {
    "haveType": "directory",
    "haveFiles": ["src/__init__.py", "src/${providerId}_provider.py"]
  }
}
```

See [`haveFiles`](../reference/predicates.md#havefiles) and [path placeholders](../reference/path-patterns.md#placeholders).

## Plugin packages

Every plugin must have specific files and exports:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "plugin-directories",
      "paths": "plugins/{pluginName}",
      "must": {
        "haveType": "directory",
        "haveFiles": ["__init__.py", "manifest.json", "README.md"]
      }
    },
    {
      "paths": "plugins/{pluginName}/__init__.py",
      "must": {
        "export": ["activate", "deactivate"],
        "exportConstants": ["PLUGIN_ID"]
      }
    }
  ]
}
```

## Barrel re-exports matching directory name

Every package `__init__.py` exposes a public name matching the directory:

```json
{
  "paths": "packages/{name}/src/__init__.py",
  "must": {
    "export": ["${name}"],
    "exportTypes": ["${name.toPascalCase()}Config"]
  }
}
```

For acronym-aware casing (`openai` → `OpenAI`), see [case-maps.md](../reference/case-maps.md).

## `__init__.py` re-export purity

Force each package `__init__.py` to be a pure barrel — only the docstring, imports, `__all__`, and re-export aliases, no local declarations or side effects:

```json
{
  "name": "init-barrels-are-pure",
  "description": "Package __init__.py files must only re-export, never declare",
  "paths": "packages/{name}/src/__init__.py",
  "must": {
    "areBarrelFiles": true
  }
}
```

A `def`, `class`, plain assignment, or top-level call in the file produces a violation. See [`areBarrelFiles`](../reference/predicates.md#arebarrelfiles).

## Re-export source pinning

Force the barrel to re-export from a specific source module (catches stray local definitions in `__init__.py`):

```json
{
  "name": "barrel-re-exports",
  "description": "Barrel files must re-export from the correct source modules",
  "paths": "packages/{providerId}/src/__init__.py",
  "must": {
    "export": [{ "name": "${providerId}", "from": ".${providerId}_provider" }],
    "exportTypes": [
      {
        "name": "${providerId.toPascalCase()}Provider",
        "from": ".${providerId}_provider"
      }
    ]
  }
}
```

The `from` field on [`export`](../reference/predicates.md#export) and [`exportTypes`](../reference/predicates.md#exporttypes) requires the export to be a re-export from the named module, matched against the specifier as written (leading relative dots included).

## Factory function with typed signature

Service factories must accept a typed config and return a typed service:

```json
{
  "description": "Each service must export a factory function with typed config param and typed return value",
  "paths": "services/{serviceName}/__init__.py",
  "must": {
    "exportFunctions": [
      {
        "name": "create_${serviceName}_service",
        "receiveParamsOfTypes": ["${serviceName.toPascalCase()}Config"],
        "returnValueOfType": "${serviceName.toPascalCase()}Service"
      }
    ]
  }
}
```

Parameter and return types are matched textually against the annotation — see [`exportFunctions`](../reference/predicates.md#exportfunctions).

## Class extending base + implementing protocol

```json
{
  "description": "Each adapter module must export a class extending BaseAdapter",
  "paths": "adapters/{adapterName}/adapter.py",
  "must": {
    "exportClasses": [
      {
        "name": "${adapterName.toPascalCase()}Adapter",
        "extend": "BaseAdapter",
        "implement": ["Connectable"]
      }
    ],
    "importTypes": [{ "name": "BaseAdapter", "from": "app.core" }]
  }
}
```

`extend` is the class's first base; `implement` covers the remaining bases. The `importTypes` rule enforces dependency direction — every adapter imports `BaseAdapter` from the core package under `TYPE_CHECKING`, not from a local copy.

## `TYPE_CHECKING` imports

Enforce that a base type is imported type-only (inside a top-level `if TYPE_CHECKING:` block), keeping it out of the runtime import graph:

```json
{
  "name": "base-imported-type-only",
  "paths": "adapters/{adapterName}/adapter.py",
  "must": {
    "importTypes": [{ "name": "BaseAdapter", "from": "app.core" }],
    "importFromExternals": true
  }
}
```

This passes for:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core import BaseAdapter
```

A plain `from app.core import BaseAdapter` (outside `TYPE_CHECKING`) would fail the `importTypes` rule. See [`importTypes`](../reference/predicates.md#importtypes).

## Protocol inheritance with `allowOmissions`

When implementations may parameterize a generic variant of the base type:

```json
{
  "name": "provider-protocol",
  "description": "Provider implementation must export a Protocol extending ProviderV1 or a variant",
  "paths": "packages/{providerId}/src/${providerId}_provider.py",
  "must": {
    "exportInterfaces": [
      {
        "name": "${providerId.toPascalCase()}Provider",
        "extend": { "type": "ProviderV1", "allowOmissions": true }
      }
    ],
    "importTypes": [{ "name": "ProviderV1", "from": "ai_toolkit.core" }]
  }
}
```

`allowOmissions` lets a `Protocol`/`ABC` satisfy the rule even when it lists `ProviderV1` as a generic argument (e.g. `class OpenAIProvider(Protocol[ProviderV1])`). See [`exportInterfaces`](../reference/predicates.md#exportinterfaces).

## Mixed severity

Hard requirement (`error`) plus a recommendation (`warning`) on the same path:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "module-must-have-init",
      "severity": "error",
      "paths": "modules/{moduleName}",
      "must": {
        "haveFiles": ["__init__.py"]
      }
    },
    {
      "name": "module-should-have-readme",
      "severity": "warning",
      "paths": "modules/{moduleName}",
      "must": {
        "haveFiles": ["README.md"]
      }
    }
  ]
}
```

Missing `__init__.py` fails CI. Missing `README.md` shows a yellow warning but doesn't block. See [Severity](../reference/configuration.md#severity).

## Path negation for known exceptions

Every package barrel exposes a public name matching the package — except `test_utils`:

```json
{
  "name": "package-barrel-exports",
  "paths": [
    "packages/{packageName}/src/__init__.py",
    "!packages/test_utils/src/__init__.py"
  ],
  "must": {
    "export": ["${packageName}"]
  }
}
```

See [path negation](../reference/path-patterns.md#negation).

## Conditional rules on optional files

Each `components/<Name>/` folder must have an `__init__.py`. Test files are optional, but when present must use the project's fixtures helper. Admin modules (also optional) must export an `ADMIN` constant:

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

Both rules enforce structural conventions that linters and the type checker won't catch: a missing `ADMIN` registration silently drops the component from the admin site, and a test that bypasses `tests.support`'s `render` skips the project's fixture setup. See [conditional-rules.md](../reference/conditional-rules.md).

## Iterating over file patterns

Every test file in a module must import the project's shared test-context helper:

```json
{
  "name": "module-tests",
  "paths": "modules/{moduleName}",
  "must": [
    {
      "for": { "files": ["test_*.py", "*_test.py"] },
      "must": { "import": [{ "name": "make_context", "from": "tests.support" }] }
    }
  ]
}
```

## Constraint-filtered subpattern

Apply different rules to AI providers (whose ID ends in `ai`) vs. other providers:

```json
{
  "paths": "packages/{providerId}",
  "must": [
    { "must": { "haveFiles": ["src/__init__.py"] } },
    {
      "if": { "placeholderSatisfies": "providerId:matches(^[a-z]+ai$)" },
      "must": { "haveFiles": ["src/${providerId}_stem.py"] }
    }
  ]
}
```

Or, equivalently, gate at the path level so the rule only matches AI providers in the first place:

```json
{
  "paths": "packages/{providerId:matches(^[a-z]+ai$)}/src/${providerId}_stem.py",
  "must": {
    "exportConstants": ["${providerId.extract(^([a-z]+)ai$)}"]
  }
}
```

See [constraints.md](../reference/constraints.md) and [`extract`](../reference/path-patterns.md#case-transformations).

## Multi-segment placeholders with `toNthSegment`

A scoped module name like `auth-session` is split, and each segment used differently:

```json
{
  "name": "scoped-modules",
  "paths": "modules/{scopedName}/src/__init__.py",
  "must": {
    "export": ["${scopedName.toNthSegment(1)}"],
    "exportTypes": [
      "${scopedName.toNthSegmentPascalCase(0)}${scopedName.toNthSegmentPascalCase(1)}"
    ]
  }
}
```

For `modules/auth-session/src/__init__.py`:
- `${scopedName.toNthSegment(1)}` → `session` (the public name)
- `${scopedName.toNthSegmentPascalCase(0)}${scopedName.toNthSegmentPascalCase(1)}` → `AuthSession` (the type name)

## Excluding specific files inside a block

```json
{
  "name": "plugin-tests",
  "paths": "plugins/{pluginName}",
  "must": [
    {
      "for": { "files": "*_test.py" },
      "excludeFiles": ["plugins/auth/helpers_test.py"],
      "must": {
        "import": [{ "name": "make_context", "from": "tests.support" }]
      }
    }
  ]
}
```

See [`excludeFiles`](../reference/conditional-rules.md#excludefiles).
