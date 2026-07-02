# Path patterns

A convention's `paths` field declares which files or directories it applies to. Path patterns combine glob syntax with **placeholders** that capture parts of the path so they can be referenced inside `must` and `mustNot` predicates.

## Glob basics

`paths` accepts a single string or an array of strings. Globs use the standard `*` (single segment), `**` (any depth), `?` (single char), and `{a,b}` (alternation) syntax.

```json
"paths": "src/**/*.py"
```

```json
"paths": [
  "packages/*/src/__init__.py",
  "apps/*/src/main.py"
]
```

## Placeholders

Wrap a path segment in `{name}` to extract it as a placeholder. The captured value becomes available inside `must` and `mustNot` predicates as `${name}`.

```json
{
  "paths": "packages/{pkgName}",
  "must": {
    "haveFiles": ["src/${pkgName}.py"]
  }
}
```

For a directory `packages/openai`, `pkgName` resolves to `"openai"`, and the rule requires `packages/openai/src/openai.py`.

A placeholder matches one path segment by default. Use it where a literal value would normally appear:

```json
"paths": "services/{svcName}/__init__.py"
```

The same placeholder can appear in both the path and the predicate values:

```json
{
  "paths": "packages/{providerId}/src/${providerId}_provider.py",
  "must": {
    "exportInterfaces": [
      { "name": "${providerId.toPascalCase()}Provider" }
    ]
  }
}
```

## Static placeholder values

Sometimes a placeholder name is used inside `must` or `mustNot`, but the consumer's tree has only one concrete value and there's no wildcard segment to capture it from. Use the optional `placeholders` field on the convention to supply the value directly:

```json
{
  "paths": "packages/openai/src/__init__.py",
  "placeholders": { "providerId": "openai" },
  "must": {
    "exportFunctions": ["create_${providerId}_provider"]
  }
}
```

This is equivalent to `paths: "packages/{providerId}/src/__init__.py"` when the tree contains exactly one provider folder, but doesn't require a wildcard. It's especially useful when consuming a [reusable convention](./reusable-conventions.md) whose predicates reference a placeholder that the local tree doesn't have a wildcard for.

A name may not appear in both a `{name}` placeholder in `paths` and in `placeholders` — pick one source of truth.

You can also inject placeholder values from the command line via the `--placeholder name:value` flag (repeatable). CLI-supplied placeholders are merged into every convention's `placeholders` map and override any existing entries there, which lets you reuse a `konsistent.json` written by someone else without forking it. CLI placeholders may not collide with names captured from `paths` — that's an error.

Values must match the same `[a-zA-Z0-9_-]+` charset as values extracted from paths. All template helpers (`toPascalCase()`, `toSnakeCase()`, etc.) work the same way as for captured placeholders.

## Case transformations

Inside `${...}` template substitutions, methods transform the captured value:

| Template | Input → output |
| --- | --- |
| `${name}` or `${name.toString()}` | raw value, e.g. `"my-thing"` |
| `${name.toPascalCase()}` | `my-thing` → `MyThing` |
| `${name.toCamelCase()}` | `my-thing` → `myThing` |
| `${name.toKebabCase()}` | `MyThing` → `my-thing` |
| `${name.toSnakeCase()}` | `MyThing` → `my_thing` |
| `${name.toConstantCase()}` | `my-thing` → `MY_THING` (uppercase snake case) |
| `${name.toFlatCase()}` | `my-thing` → `mything` |
| `${name.toNthSegment(0)}` | `my-thing` → `my` (split by `-`, return nth segment) |
| `${name.toNthSegmentPascalCase(1)}` | `my-thing` → `Thing` |
| `${name.toNthSegmentCamelCase(1)}` | `my-thing` → `thing` |
| `${name.extract(regex)}` | `openai` with `^([a-z]+)ai$` → `open` |

`extract` returns the first capture group when the regex has groups; otherwise it returns the full match. An empty string is returned when the regex does not match. Patterns compile with Python's `re` module — see [constraints.md](./constraints.md#divergence-from-js-regexp) for the small divergence surface.

The `toNthSegment*` helpers split on `-` only. (The `segments(n)` constraint additionally splits on `_` and camelCase boundaries — see [constraints.md](./constraints.md#segmentsn).)

The argument inside `(...)` is taken verbatim — no surrounding quotes. The argument may not contain `}` (use repetition like `\d\d?` instead of `\d{1,2}` if you need quantifiers).

For acronyms like `openai` → `OpenAI` instead of `Openai`, declare overrides with [`kebabToPascalMap`](./case-maps.md).

### Template substitutions in predicates

Templates work anywhere a string appears in `must` or `mustNot`:

```json
{
  "paths": "adapters/{adapterName}/factory.py",
  "must": {
    "exportFunctions": [
      {
        "name": "create_${adapterName}_adapter",
        "receiveParamsOfTypes": [
          "${adapterName.toPascalCase()}AdapterConfig"
        ],
        "returnValueOfType": "${adapterName.toPascalCase()}Adapter"
      }
    ]
  }
}
```

For `adapters/postgres/factory.py`, the rule requires `create_postgres_adapter` with parameter type `PostgresAdapterConfig` and return type `PostgresAdapter`.

## Path placeholder constraints

Placeholders accept inline constraints with `{name:constraint(arg)}`. Paths whose extracted value fails a constraint are skipped — the rule does not apply.

```json
"paths": "packages/{providerId:matches(^[a-z]+ai$)}/src/${providerId}_stem.py"
```

For the constraint catalog (`matches`, `segments`), syntax rules, and use in `if.placeholderSatisfies` blocks, see [constraints.md](./constraints.md).

## Negation

Prefix a pattern with `!` to exclude paths matched by other entries. Negation is most useful for known exceptions:

```json
{
  "paths": [
    "packages/{packageName}/src/__init__.py",
    "!packages/test_utils/src/__init__.py"
  ],
  "must": {
    "export": ["${packageName}"]
  }
}
```

Every package barrel must export a name matching the package, except `test_utils`.

For excluding files based on a sub-pattern within matched paths, see [`excludeFiles`](./configuration.md#excludefiles) on the convention or block.

## Multiple path entries

`paths` as an array runs the rule against the union of all matches:

```json
"paths": [
  "src/components/**/*.py",
  "src/widgets/**/*.py"
]
```

Combine with negation to compose include/exclude lists.

## Matching files vs. directories

Glob results include both files and directories. Use `haveType` to assert which one is expected:

```json
{
  "paths": "packages/{name}",
  "must": { "haveType": "directory" }
}
```

When the path's last segment ends with a file extension (e.g. `.py`), only files match. When it ends in a placeholder (e.g. `{name}`) without an extension, both can match — be explicit with `haveType` or narrow the pattern (`packages/{name}/`).
