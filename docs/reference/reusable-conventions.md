# Reusable conventions

Reusable conventions let a `konpy.json` consume conventions shared from another JSON file, instead of restating every rule in full. A reusable convention is a JSON record produced by an author, bound to a local **vendor prefix** in the consumer's config, and referenced from `conventions[]` either as a string or as an object with overrides.

This page is the consumer-facing reference. To publish your own reusable conventions, see [the authoring guide](../guides/authoring-reusable-conventions.md).

## When to use

- A library author ships a curated set of conventions that consumers of the library should adopt.
- An organization shares an internal "house style" set of conventions across many repos.
- A monorepo wants one canonical set of conventions reused across packages.

For any of those cases, the consumer adds one entry to `conventionSources` and references each convention by name.

If reusable conventions contain plugin predicate keys, the consuming config must also list the plugin distribution in top-level `plugins`. Convention sources do not automatically load plugins.

## `conventionSources`

`conventionSources` is a top-level field in `konpy.json`. Each key is a local **vendor prefix** (matches `[a-z0-9-]+`); each value is either a **local path** to a JSON convention package or the name of an installed Python distribution that contains one:

| Value shape | Interpretation |
| --- | --- |
| Starts with `.` or is absolute | Relative or absolute path to a JSON file. Relative paths resolve against the config file's directory (not the current working directory). |
| Bare Python distribution name | Installed distribution lookup. `konpy` looks for `<top-level import package>/konpy.json`, then for a `konpy.json` file listed among the distribution's `.dist-info` files. |
| Contains `/` or npm-style `@scope/pkg` syntax | Invalid Python distribution name. Use a local path or a valid installed Python distribution name. |

Installed distribution names must match `[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]`.

A convention source loaded from a package must be a reusable-conventions package, not a full config:

```json
{
  "conventionSpecVersion": "v1",
  "conventions": []
}
```

This is intentionally different from package-backed `extends`, whose `konpy.json` is a full config with `"version": "v1"` — see [configuration.md](./configuration.md#config-inheritance).

The vendor prefix is local to your config — you can bind any prefix to any source. Two configs in the same monorepo can pick different prefixes for the same upstream file or distribution without conflict.

```json
{
  "$schema": "./konpy.schema.json",
  "version": "v1",
  "plugins": ["acme-konpy-rules"],
  "conventionSources": {
    "common": "./conventions/common.json",
    "shared": "acme-konpy-conventions"
  },
  "conventions": []
}
```

`conventionSources` is optional. Existing configs without it keep working unchanged.

## Referencing a convention

Each entry of `conventions[]` is one of three shapes. The first two are for reusable conventions; the third is the existing hand-written form.

### String reference

A bare string `"<vendor>/<name>"` inlines the named reusable convention as-is. The reusable convention must declare its own `paths` — string references cannot supply them. If the convention has no `paths`, `konpy` fails at config load and tells you to switch to the `use` form.

```json
{
  "version": "v1",
  "conventionSources": {
    "common": "./conventions/common.json"
  },
  "conventions": [
    "common/package-dir-must-have-readme-file"
  ]
}
```

### Object reference (`use` form)

`{ "use": "<vendor>/<name>", ...overrides }` references a reusable convention and overlays your overrides on top of it. The override fields available are `paths`, `placeholders`, `excludeFiles`, `severity`, `if`, `for`, `must`, and `mustNot` — the same optional fields a hand-written convention has, minus `name`, `description`, and `hint` (which come from the source and are not overridable at this nesting level; use the `must[]` array form's `{ "use": ..., "description": ..., "hint": ... }` overrides instead if you need to customize them per-block).

Use this form when the reusable convention has no `paths` (so you must supply them) or when you want to adjust a field for your project.

```json
{
  "version": "v1",
  "conventionSources": {
    "common": "./conventions/common.json"
  },
  "conventions": [
    {
      "use": "common/module-must-export-equivalent-function",
      "paths": ["src/commands/{commandName}.py"]
    },
    {
      "use": "common/every-py-file-must-have-tests",
      "excludeFiles": ["**/conftest.py", "src/legacy/**"]
    }
  ]
}
```

When a reusable convention's `must` references a placeholder (e.g. `${providerId}`) and your project has only a single concrete value rather than a wildcard segment, supply it via `placeholders`:

```json
{
  "use": "common/provider-barrel",
  "paths": "packages/openai/src/__init__.py",
  "placeholders": { "providerId": "openai" }
}
```

See [Static placeholder values](./path-patterns.md#static-placeholder-values) for the full rules.

### Hand-written convention

Any entry that is neither a string nor has a `use` key is treated as a hand-written `Convention` and validated against the existing schema. See [configuration.md](./configuration.md). You can mix all three forms in the same `conventions[]` array.

### `use` inside a parent's `must[]`

A hand-written convention whose `must` is a `MustBlock[]` may also reference a reusable convention from inside the array, in either the bare-string or the object (`use`) form. Both expand into a single `MustBlock` rather than a full `Convention`. The bare-string form does not require the source convention to declare `paths` (a top-level requirement only) — `paths` belongs to the parent convention.

```json
{
  "version": "v1",
  "conventionSources": {
    "common": "./local-conventions.json"
  },
  "conventions": [
    {
      "name": "package-folder-shape",
      "paths": ["src/packages/{packageName}"],
      "must": [
        { "must": { "haveType": "directory" } },
        { "use": "common/must-have-init" }
      ]
    }
  ]
}
```

Allowed override keys at this nesting level are every field a hand-written `MustBlock` exposes — `name`, `description`, `hint`, `if`, `for`, `excludeFiles`, `must`, and `mustNot`. Top-level-only fields (`paths`, `severity`) are not accepted at the use-site, and the referenced reusable convention must not declare them either: a reusable that ships `paths` or `severity` can only be referenced from the top level of `conventions[]`. Authors who want their reusable to be usable in both contexts should publish it without those fields.

Override merge follows the same rules as the top-level `use` form: arrays replace, primitives replace, and `must`/`mustNot` deep-merge with the inherited predicates.

## Plugin predicates in reusable conventions

Reusable conventions may use plugin predicate keys:

```json
{
  "conventionSpecVersion": "v1",
  "conventions": [
    {
      "name": "acme-marker",
      "description": "Every source file carries the Acme marker.",
      "paths": "src/*.py",
      "must": {
        "acmeMarker": "ACME_OK"
      }
    }
  ]
}
```

The consumer must opt into the plugin distribution:

```json
{
  "version": "v1",
  "plugins": ["acme-konpy-rules"],
  "conventionSources": {
    "acme": "acme-konpy-conventions"
  },
  "conventions": ["acme/acme-marker"]
}
```

`conventionSources` only loads reusable convention data. It does not load predicate plugins from the convention package automatically, even if the same distribution also exposes `konpy.predicates` entry points. This keeps plugin code execution explicit through `plugins`.

See [plugins.md](./plugins.md).

## Merge semantics

When you write `{ use: "<vendor>/<name>", ...overrides }`, `konpy` deep-merges your overrides on top of the reusable convention with these rules:

| Field kind | Rule |
| --- | --- |
| Plain object (e.g. `must`, `mustNot`, nested predicate definitions) | Recursive deep-merge. Keys you supply replace the inherited value; keys you omit pass through. |
| Array (e.g. `paths`, `excludeFiles`, predicate lists like `haveFiles`, `declareFunctions`, `export`, `exportFunctions`) | Your array fully replaces the inherited array. Use `"excludeFiles": []` to clear an inherited list. |
| Primitive (e.g. `severity`, `description`) | Your value replaces the inherited value. |

Arrays replace rather than concatenate so you can subtract from a shared convention, not just append. If you want to extend an inherited array, copy it into your override and add to it.

### Before / overrides / after

Given this reusable convention:

```json
{
  "name": "every-py-file-must-have-tests",
  "description": "Every Python file in src/ ...",
  "paths": ["src/{name:matches(^[^.]+$)}.py"],
  "excludeFiles": ["legacy.py"],
  "must": {
    "haveFiles": ["test_${name}.py"]
  }
}
```

And this consumer entry:

```json
{
  "use": "common/every-py-file-must-have-tests",
  "excludeFiles": ["**/conftest.py"],
  "must": {
    "haveType": "file"
  }
}
```

The expanded convention `konpy` runs is:

```json
{
  "name": "every-py-file-must-have-tests",
  "description": "Every Python file in src/ ...",
  "paths": ["src/{name:matches(^[^.]+$)}.py"],
  "excludeFiles": ["**/conftest.py"],
  "must": {
    "haveFiles": ["test_${name}.py"],
    "haveType": "file"
  }
}
```

Note that `excludeFiles` was fully replaced (array-replace), while `must` was deep-merged (`haveType` added without dropping the inherited `haveFiles`).

## Restrictions

- **Reusable conventions only support object-form `must` and `mustNot`.** They cannot ship the `MustBlock[]` form. This keeps override semantics predictable — you always know the merge target is a flat predicate object. Your own hand-written conventions can still use `MustBlock[]` in `must`; `mustNot` is object-form only everywhere. See [predicates.md](./predicates.md).
- **Plugin predicates require explicit consumer opt-in.** If a reusable convention contains plugin keys, the consuming `konpy.json` must list the plugin distribution in top-level `plugins`. Convention sources do not auto-load plugin entry points.
- **The `conventionSources` value is a single string.** No object form (`{ path: ... }`) — auto-detection by leading `.` / absolute path is unambiguous.
- **Package convention sources are installed Python distributions.** Bare values are resolved with Python packaging metadata. npm-style specifiers such as `@scope/pkg` and subpaths such as `pkg/subpath` are invalid.
- **Package convention sources must ship reusable packages.** Their `konpy.json` must use `conventionSpecVersion: "v1"`, not `version: "v1"`.
- **No cross-source merging.** Two `conventionSources` entries cannot be merged into a single prefix. If two files happen to ship a convention with the same name, your vendor prefix scopes them.
- **`MustBlock[]` cannot be introduced via override.** Because the source convention's `must` is always object-form, deep-merge keeps the result object-form.

## Placeholder validation

After expansion, `konpy` walks every string inside each merged convention's `must` and `mustNot` and checks that each `${placeholder}` referenced is declared as `{placeholder}` in at least one `paths` entry (or in `placeholders`). This catches mismatches between a reusable convention's templates and the `paths` you supplied at the use-site, before any file is scanned.

Plugin predicate values are also scanned recursively by default when the plugin descriptor has `validate_placeholders=True`.

## Error reference

All errors below are surfaced by the CLI before any scanning starts.

| Condition | Error string | What to do |
| --- | --- | --- |
| Unknown vendor prefix | `Unknown convention source "<prefix>" referenced in conventions[<i>]. Declare it in conventionSources or fix the typo.` | Add an entry to `conventionSources`, or correct the prefix in the reference. |
| Unknown convention name within a source | `No convention "<name>" in source "<prefix>". The package exports: <list>.` | Pick one of the listed names, or check that you reference the right version of the source file. |
| Malformed reference string | `Invalid convention reference "<ref>" in conventions[<i>]. Expected format "<vendor>/<name>".` | Fix the reference to the `<vendor>/<name>` shape. |
| String-form reference to a paths-less convention | `Convention "<prefix>/<name>" cannot be referenced by string; it has no "paths". Use { use: "<prefix>/<name>", paths: [...] } form.` | Switch to the `use` form and supply `paths` for your project. |
| `use` reference with no `paths` on either side | `Convention "<prefix>/<name>" referenced in conventions[<i>] has no "paths". Either the reusable convention must declare paths, or the override must supply paths.` | Add `paths` to your override. |
| Invalid package source name | `Convention source "<prefix>" → "<value>": invalid Python distribution name. Bare package sources must match [A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9].` | Use a valid Python distribution name, or a local path beginning with `.` / an absolute path. |
| Package source not installed | `Convention source "<prefix>" → "<value>": installed Python distribution not found. Install it or use a local path in conventionSources.` | Install the distribution into the environment running `konpy`, or use a local file. |
| Package source has no `konpy.json` | `Convention source "<prefix>" → "<value>": installed Python distribution does not contain konpy.json. Looked for <top-level import package>/konpy.json and a distribution file named konpy.json.` | Add package data at the import package root, or include `konpy.json` in the distribution's `.dist-info` files. |
| Path source unreadable | `Convention source "<prefix>" → "<value>": could not read file at <path>.` | Check the path exists and is readable. |
| Source malformed JSON | `Convention source "<prefix>" → "<value>": malformed JSON at <location>.` | Fix the JSON. |
| Reusable-convention package fails schema validation | `Convention source "<prefix>" → "<value>": invalid reusable-convention package at <location>: <issues>` | Fix the convention package to match the reusable-conventions schema. |
| Empty source value | `Convention source "<prefix>" has empty value.` | Supply a path or installed distribution name. |
| `use` inside `must[]` points at a reusable that declares `paths`/`severity` | `Convention "<prefix>/<name>" referenced in conventions[<i>].must[<j>] declares top-level-only field(s) "<field>". Such conventions can only be referenced at the top level of conventions[]. Either remove the field(s) from the source convention, or move the reference out of must[].` | Drop `paths`/`severity` from the reusable, or reference it directly from `conventions[]`. |
| Placeholder used in `must` or `mustNot` but not declared in `paths` or `placeholders` | `Convention "<identifier>" references "${<placeholder>}" in <key>, but neither paths nor placeholders declare "{<placeholder>}".` | Either declare the placeholder in `paths` or `placeholders`, or remove the unresolved template. |
| Plugin predicate key used without opt-in | Validation error containing `unknown predicate key "<key>"`. | Add the plugin distribution to top-level `plugins`, or remove/fix the predicate key. |

`<identifier>` in the placeholder error is the convention's `name`, the `<vendor>/<name>` reference, or `conventions[<i>]` — whichever was available.

## See also

- [Authoring reusable conventions](../guides/authoring-reusable-conventions.md) — publish your own.
- [konpy.json reference](./configuration.md) — the surrounding config shape.
- [Predicates](./predicates.md) — built-in and plugin predicate behavior.
- [Plugins](./plugins.md) — custom predicate entry points and descriptor API.
- [Path patterns](./path-patterns.md) — placeholder syntax used in `paths`, `must`, and `mustNot`.
