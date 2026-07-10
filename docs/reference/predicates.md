# Predicates

Predicates are the assertions inside a convention's `must` or `mustNot` block. Each predicate checks one structural property of the matched path. Listing multiple predicates in the same `must` is equivalent to AND — they all must pass. Listing predicates in `mustNot` reverses the result — a matched path fails when it satisfies one of those predicates.

`konpy` parses each Python module with the standard-library `ast` module. The definitions of "export", "type", "interface", and "import" below are all expressed in those Python terms.

## What counts as an export

Because Python has no `export` keyword, the public API of a module is defined as:

- Every name listed in `__all__` when `__all__` is assigned a **literal** list/tuple of strings, **or**
- If there is no literal `__all__`, every top-level name **without a leading underscore**.

Kind-specific export predicates then narrow that public set:

| Predicate | Public symbol it accepts |
| --- | --- |
| `export` | any public name (function, class, constant, assignment, or re-export) |
| `exportTypes` | public type aliases — PEP 695 `type X = ...` and `X: TypeAlias = ...` — plus `Protocol`/`ABC` classes |
| `exportConstants` | public `UPPER_CASE` assignments and `Final`-annotated assignments |
| `exportFunctions` | public `def`/`async def` |
| `exportInterfaces` | public `Protocol`/`ABC` classes only |
| `exportClasses` | public `class` declarations |

The matching `declare*` variants assert a symbol is present at module level **and not public** (either absent from a literal `__all__`, or leading-underscore when `__all__` is dynamic/absent).

## Built-in and plugin predicates

The catalog below documents built-in predicates. Configs may also opt into plugin predicates through top-level `plugins`.

```json
{
  "version": "v1",
  "plugins": ["acme-konpy-rules"],
  "conventions": [
    {
      "paths": "src/*.py",
      "must": {
        "acmeMarker": "ACME_OK"
      }
    }
  ]
}
```

Plugin predicate keys remain strict: unknown keys are rejected unless a named plugin distribution declares them. See [plugins.md](./plugins.md) for entry-point loading, descriptor shape, value validation, `mustNot`, and public plugin-author imports.

## Catalog

- [Filesystem predicates](#filesystem-predicates)
  - [`haveType`](#havetype)
  - [`haveFiles`](#havefiles)
  - [`matchContent`](#matchcontent)
  - [`havePairedFile`](#havepairedfile)
- [Declaration predicates](#declaration-predicates)
  - [`declareTypes`](#declaretypes)
  - [`declareConstants`](#declareconstants)
  - [`declareFunctions`](#declarefunctions)
  - [`declareInterfaces`](#declareinterfaces)
  - [`declareClasses`](#declareclasses)
- [Export predicates](#export-predicates)
  - [`export`](#export)
  - [`exportTypes`](#exporttypes)
  - [`exportConstants`](#exportconstants)
  - [`exportFunctions`](#exportfunctions)
  - [`exportInterfaces`](#exportinterfaces)
  - [`exportClasses`](#exportclasses)
- [Import predicates](#import-predicates)
  - [`import`](#import)
  - [`importFrom`](#importfrom)
  - [`importTypes`](#importtypes)
  - [`importFromCurrentDir`](#importfromcurrentdir)
  - [`importFromParents`](#importfromparents)
  - [`importFromExternals`](#importfromexternals)
  - [`importTypesFromCurrentDir`](#importtypesfromcurrentdir)
  - [`importTypesFromParents`](#importtypesfromparents)
  - [`importTypesFromExternals`](#importtypesfromexternals)
- [Structural predicates](#structural-predicates)
  - [`useDeclarationOrder`](#usedeclarationorder)
  - [`areBarrelFiles`](#arebarrelfiles)
  - [`haveDocstrings`](#havedocstrings)
  - [`annotateFunctions`](#annotatefunctions)
  - [`restrictAnnotations`](#restrictannotations)
  - [`restrictRepeatedLiterals`](#restrictrepeatedliterals)
  - [`restrictDuplicateFunctions`](#restrictduplicatefunctions)
- [Plugin predicates](#plugin-predicates)

Most predicates support template substitutions in their string values — see [path-patterns.md](./path-patterns.md#case-transformations) for the full case-transformation catalog. Exceptions: `matchContent` regex patterns are compiled as written and do **not** perform template substitution, because `${...}` is valid regex syntax; `restrictAnnotations`, `restrictRepeatedLiterals`, and `restrictDuplicateFunctions` option patterns also do **not** perform template substitution, because they match parsed source facts exactly.

`mustNot` accepts only the object form:

```json
"mustNot": {
  "exportConstants": ["DEBUG"]
}
```

It does not accept `MustBlock[]` or reusable-convention references.

---

## Filesystem predicates

### `haveType`

Assert that the matched path is a file or a directory.

```json
"must": { "haveType": "directory" }
```

```json
"must": { "haveType": "file" }
```

Values: `"file"` or `"directory"`.

Use this when a glob pattern could match either (e.g., `packages/{name}` could match a file or directory) and you want to be explicit.

### `haveFiles`

Assert that specific files exist within the matched path. Used with directory paths.

```json
{
  "paths": "packages/{providerId}",
  "must": {
    "haveType": "directory",
    "haveFiles": ["src/__init__.py", "src/${providerId}_provider.py"]
  }
}
```

For `packages/openai`, this requires both `packages/openai/src/__init__.py` and `packages/openai/src/openai_provider.py` to exist. Templates resolve from the parent path placeholders.

`haveFiles` paths are relative to the matched directory and may contain forward slashes for nested paths.

### `matchContent`

Assert that the matched file's text contains content matching each configured Python regular expression.

```json
"must": {
  "matchContent": ["SPDX-License-Identifier: Apache-2.0", "^class Service"]
}
```

Values: a non-empty array of non-empty strings. Each string is compiled with Python `re` and searched against the file contents with multiline matching enabled, so `^` and `$` can match line boundaries.

Use this for required content such as license headers, generated-code markers, encoding pragmas, or simple project-specific text rules.

In `mustNot`, `matchContent` forbids matching content and is evaluated item-by-item:

```json
"mustNot": {
  "matchContent": ["TODO", "password\\s*="]
}
```

`matchContent` patterns are regular expressions, not templates. They are compiled exactly as written and do **not** perform placeholder substitution.

### `havePairedFile`

Assert that a single paired file exists relative to the repository root.

```json
{
  "paths": "src/{name}.py",
  "must": {
    "havePairedFile": "tests/test_${name}.py"
  }
}
```

For `src/service.py`, this requires `tests/test_service.py`.

Unlike `haveFiles`, `havePairedFile` is resolved against the repo root, not the matched file's directory. Template substitutions are supported using the same placeholder grammar as other string-valued predicates.

Value: a single non-empty string.

---

## Declaration predicates

Declaration predicates assert local declarations that must **not** be part of the module's public API. They mirror the kind-specific export predicates, but expect module-level symbols that are private (absent from a literal `__all__`, or leading-underscore) — such as `_default_options = ...` or `def _create_value(): ...`.

All declaration predicates accept an array of bare strings or objects with a `name` field. The string form is shorthand for `{ "name": "<value>" }`.

### `declareTypes`

Assert local type declarations. PEP 695 `type X = ...`, `X: TypeAlias = ...`, and `Protocol`/`ABC` classes qualify.

```json
"must": { "declareTypes": ["_InternalConfig"] }
```

### `declareConstants`

Assert local constant declarations (`UPPER_CASE` or `Final`-annotated).

```json
"must": { "declareConstants": ["_DEFAULT_OPTIONS"] }
```

### `declareFunctions`

Assert local function declarations. Optionally validate parameters and return type, using the same fields as `exportFunctions`.

```json
"must": {
  "declareFunctions": [
    {
      "name": "_create_internal_client",
      "receiveParamsOfTypes": ["ClientConfig"],
      "returnValueOfType": "Client"
    }
  ]
}
```

### `declareInterfaces`

Assert local `Protocol`/`ABC` declarations. Optionally validate `extend`, using the same fields as `exportInterfaces`.

```json
"must": {
  "declareInterfaces": [
    { "name": "_InternalClient", "extend": "BaseClient" }
  ]
}
```

### `declareClasses`

Assert local class declarations. Optionally validate `extend` and `implement`, using the same fields as `exportClasses`.

```json
"must": {
  "declareClasses": [
    {
      "name": "_InternalClient",
      "extend": "BaseClient",
      "implement": ["Disposable"]
    }
  ]
}
```

---

## Export predicates

All export predicates accept an array of either:
- A bare string (the expected export name), or
- An object with a `name` field plus optional metadata.

The string form is shorthand for `{ "name": "<value>" }`.

### `export`

Assert public value exports — any public name that is not a type-only export. Functions, classes, constants, and re-exported values all qualify.

```json
"must": { "export": ["my_function", "${name}"] }
```

```json
"must": {
  "export": [
    { "name": "${providerId}", "from": ".${providerId}_provider" }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The export name. Templates allowed. |
| `from` | string | Optional. If set, the export must be a re-export whose module specifier matches this value. |

When `from` is omitted, only the export's existence is checked. When `from` is set, the export must be a re-export from that source (`from .x import name`) — useful for enforcing `__init__.py` structure. The `from` value is matched against the specifier **as written**, including leading relative dots (see [`import`](#import)).

### `exportTypes`

Assert public type exports. PEP 695 `type X = ...`, `X: TypeAlias = ...`, and `Protocol`/`ABC` classes match.

```json
"must": {
  "exportTypes": ["${name.toPascalCase()}Config"]
}
```

```json
"must": {
  "exportTypes": [
    {
      "name": "${providerId.toPascalCase()}Provider",
      "from": ".${providerId}_provider"
    }
  ]
}
```

Same shape as `export`: bare string or `{ name, from? }`.

### `exportConstants`

Assert constant exports specifically. Stricter than `export` — a `def` or a lowercase assignment with the right name will not satisfy this predicate. A public `UPPER_CASE` assignment or a `Final`-annotated assignment qualifies.

```json
"must": {
  "exportConstants": ["PLUGIN_ID", "DEFAULT_CONFIG"]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The constant name. Templates allowed. |

### `exportFunctions`

Assert function exports. Optionally validate parameters and return type.

```json
"must": {
  "exportFunctions": [
    {
      "name": "create_${serviceName}_service",
      "receiveParamsOfTypes": ["${serviceName.toPascalCase()}Config"],
      "returnValueOfType": "${serviceName.toPascalCase()}Service"
    }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The function name. Templates allowed. |
| `receiveParamsOfTypes` | string[] | Optional. Ordered parameter types to enforce by index. Extra function parameters are allowed. |
| `receiveParamOfType` | string | Deprecated. Optional type at least one parameter must have. Use `receiveParamsOfTypes` instead. |
| `returnValueOfType` | string | Optional. Type the return value must have. |

Types are matched **textually** against each annotation (normalized with `ast.unparse`): the expected value matches either the full annotation text or its base name with any subscript stripped. So `returnValueOfType: "Service"` matches an annotation `Service`, `Service[int]`, or `list[Service]`'s base — write the exact annotation text you expect, or the un-subscripted base name.

The bare-string form (`"exportFunctions": ["my_function"]`) checks existence only.

### `exportInterfaces`

Assert `Protocol`/`ABC` exports. Type aliases do **not** satisfy this predicate. Optionally validate the base classes.

```json
"must": {
  "exportInterfaces": [
    { "name": "${providerId.toPascalCase()}Provider", "extend": "ProviderV1" }
  ]
}
```

```json
"must": {
  "exportInterfaces": [
    {
      "name": "${providerId.toPascalCase()}Provider",
      "extend": { "type": "ProviderV1", "allowOmissions": true }
    }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The interface name. Templates allowed. |
| `extend` | string \| `{ type, allowOmissions? }` | Optional. Base the class must list. `extend` matches **any** base name. |

When `extend` is the object form with `allowOmissions: true`, the interface also satisfies the rule when it lists the base's **first generic argument** (e.g. `class X(Protocol[ProviderV1])`) — useful when implementations parameterize the base type.

### `exportClasses`

Assert class exports. Optionally validate the base classes: `extend` is the **first** base, and `implement` lists the **remaining** bases.

```json
"must": {
  "exportClasses": [
    {
      "name": "${adapterName.toPascalCase()}Adapter",
      "extend": "BaseAdapter",
      "implement": ["Connectable", "Disposable"]
    }
  ]
}
```

For `class PostgresAdapter(BaseAdapter, Connectable, Disposable): ...`, `extend` is `BaseAdapter` (first base) and `implement` covers `Connectable` and `Disposable` (the rest).

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The class name. Templates allowed. |
| `extend` | string \| `{ type, allowOmissions? }` | Optional. The class's first base. |
| `implement` | array of (string \| `{ type, allowOmissions? }`) | Optional. The class's remaining bases. |

`allowOmissions` works the same as in `exportInterfaces` — the class also satisfies the rule when it lists a generic variant of the base (its first generic argument).

---

## Import predicates

A "type-only" import in Python is one written inside a top-level `if TYPE_CHECKING:` block. Everything else is a value import.

### `import`

Assert named value imports (`from x import name`).

```json
"must": {
  "import": [
    { "name": "BaseModel", "from": "pydantic" }
  ]
}
```

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The imported binding. Templates allowed. |
| `from` | string | Optional. Module specifier the import must come from. |

Bare-string form (`"import": ["BaseModel"]`) checks the binding regardless of source.

The `from` value is compared against the module specifier **as written**, including leading relative dots. `".base"` matches `from .base import X`; `"..types"` matches `from ..types import X`. A **bare** module such as `"pkg"` also prefix-matches submodules (`pkg.sub`), while a **dotted-relative** specifier matches exactly.

### `importFrom`

Assert that the file has at least one import statement from a specific module path or package.

```json
"must": { "importFrom": "pydantic" }
```

```json
"must": { "importFrom": ".setup" }
```

The value is a string. Relative specifiers (with leading dots) are matched exactly, so `".setup"` only matches `from .setup import ...` (or `from . import setup`'s specifier as written).

Bare package roots match the package itself and its subpaths. For example, `"pydantic"` matches imports from `pydantic` and `pydantic.fields`. Similarly named packages such as `pydantic_core` do not match.

Both value imports and type-only imports count because this predicate checks import statements by source.

### `importTypes`

Assert type-only imports — named imports inside a top-level `if TYPE_CHECKING:` block.

```json
"must": {
  "importTypes": [
    { "name": "ProviderV1", "from": "ai_toolkit.core" }
  ]
}
```

Same shape as `import`. Useful for enforcing dependency direction — every adapter's implementation module must import its base type from a specific module under `TYPE_CHECKING`.

### `importFromCurrentDir`

Assert whether the file has value imports from the current package (relative level 1).

```json
"must": { "importFromCurrentDir": true }
```

`true` requires at least one non-type import at relative level 1 (`from . import x`, `from .foo import y`). `false` forbids those imports. Type-only imports (inside `TYPE_CHECKING`) are ignored.

### `importFromParents`

Assert whether the file has value imports from parent packages (relative level ≥ 2).

```json
"must": { "importFromParents": false }
```

`true` requires at least one non-type import at relative level 2 or deeper (`from .. import x`, `from ..types import y`). `false` forbids those imports. Type-only imports are ignored.

### `importFromExternals`

Assert whether the file has value imports from absolute (non-relative) module specifiers.

```json
"must": { "importFromExternals": true }
```

`true` requires at least one non-type absolute import (`import os`, `from pydantic import BaseModel`). `false` forbids those imports. Any absolute specifier counts as external because `konpy` does not resolve whether it points inside or outside the project. Type-only imports are ignored.

### `importTypesFromCurrentDir`

Assert whether the file has type-only imports from the current package (relative level 1).

```json
"must": { "importTypesFromCurrentDir": true }
```

`true` requires at least one type import at relative level 1. `false` forbids those imports. Value imports are ignored.

### `importTypesFromParents`

Assert whether the file has type-only imports from parent packages (relative level ≥ 2).

```json
"must": { "importTypesFromParents": false }
```

`true` requires at least one type import at relative level 2 or deeper. `false` forbids those imports. Value imports are ignored.

### `importTypesFromExternals`

Assert whether the file has type-only imports from absolute module specifiers.

```json
"must": { "importTypesFromExternals": true }
```

`true` requires at least one absolute type import. `false` forbids those imports. Value imports are ignored.

---

## Structural predicates

### `useDeclarationOrder`

Assert relative order for selected symbols.

```json
"must": {
  "useDeclarationOrder": ["schema", "parse_input", "format_output"]
}
```

The configured array is the expected order. Only symbols that are present in the file are checked; missing symbols do not produce diagnostics. Module-level named symbols — `def`/`class` declarations and top-level assignments — are ordered by their position in the file.

### `areBarrelFiles`

Assert that the matched files are pure `__init__.py` re-export files: every top-level statement must be an import, a re-export, an `__all__` declaration, or the module docstring — not a local declaration or a side-effecting statement.

```json
{
  "paths": "src/{package_name}",
  "must": [
    {
      "for": { "files": "__init__.py" },
      "must": { "areBarrelFiles": true }
    }
  ]
}
```

A file passes when every top-level statement is one of:

- The module docstring.
- An `import` / `from ... import ...` statement of any form, including star imports (`from .submodule import *`).
- An `__all__` assignment or augmentation (`__all__ = [...]`, `__all__ += [...]`).
- A public alias re-export: `name = imported_name`, where the right-hand side is a bare name brought in by an `import` statement in the same file.
- A top-level `if TYPE_CHECKING:` block.

Every other top-level construct produces a diagnostic:

| Violation kind | Example | Message |
| --- | --- | --- |
| `declaration` | `def f(): ...`, `class C: ...`, `x = compute()`, `CONST = 1`, `type T = ...` | `Barrel file must not contain declarations` |
| `expression` | `configure()`, `print("hi")` | `Barrel file must not contain top-level expression statements` |

The predicate takes a bare boolean (`true` enables, `false`/omitted disables). It does not enforce a filename — pair it with a `for` block or a `paths` pattern that targets the `__init__.py` files you consider barrels.

### `haveDocstrings`

Assert that selected module, class, function, and method targets have docstrings.

```json
"must": { "haveDocstrings": true }
```

The bare `true` form checks:

- the module docstring;
- public top-level classes;
- public top-level functions;
- public methods directly inside public top-level classes.

Public top-level symbols use the same publicness rules as exports: literal `__all__` when present, otherwise names without a leading underscore. Public methods are methods directly inside public top-level classes whose names do not start with `_`.

Use the object form to choose targets:

```json
"must": {
  "haveDocstrings": {
    "modules": true,
    "classes": true,
    "functions": true,
    "publicOnly": true
  }
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `modules` | boolean | `true` | Check the module docstring. |
| `classes` | boolean | `true` | Check top-level class docstrings. |
| `functions` | boolean | `true` | Check top-level function and direct-method docstrings. |
| `publicOnly` | boolean | `true` | Skip private classes, functions, and methods. The module docstring is always considered public. |

Objects that disable all of `modules`, `classes`, and `functions` are invalid.

Nested local functions and nested classes are not checked.

### `annotateFunctions`

Assert annotation coverage for selected function definitions.

```json
"must": { "annotateFunctions": true }
```

The bare `true` form requires every selected public top-level function and public direct method to have:

- a return type annotation;
- a type annotation for every selected parameter.

For direct methods, the first `self` or `cls` parameter is ignored. Parameter coverage includes positional-only parameters, regular positional parameters, keyword-only parameters, `*args`, and `**kwargs`.

Use the object form to choose checks:

```json
"must": {
  "annotateFunctions": {
    "returns": true,
    "params": true,
    "publicOnly": true
  }
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `returns` | boolean | `true` | Require return type annotations. |
| `params` | boolean | `true` | Require parameter type annotations. |
| `publicOnly` | boolean | `true` | Skip private top-level functions, private classes' methods, and methods whose names start with `_`. |

Objects that disable both `returns` and `params` are invalid.

This is a coverage-style predicate: it checks all selected/public function definitions in the matched file. It differs from `exportFunctions`, which checks specific named exported functions and optional signature details.

Nested local functions and methods on nested classes are not checked.

### `restrictAnnotations`

Flag identity-less anonymous record annotations and suggest replacing them with named record types.

```json
"must": { "restrictAnnotations": true }
```

The bare `true` form enables the default rules with `publicOnly: true`.

Use the object form to customize matching:

```json
"must": {
  "restrictAnnotations": {
    "forbid": ["dict[str, *]"],
    "allow": ["dict[str, JsonValue]"],
    "defaults": true,
    "publicOnly": true
  }
}
```

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `forbid` | string[] | unset | Additional annotation patterns to forbid. Patterns match normalized `ast.unparse` annotation text. |
| `allow` | string[] | unset | Annotation patterns to allow even when they match `forbid` or the defaults. |
| `defaults` | boolean | `true` | Enable the built-in anonymous-record defaults. |
| `publicOnly` | boolean | `true` | Skip private functions/methods, private module constants, and private class attributes. |

`forbid` and `allow` use fnmatch-style `*` wildcards against normalized annotation text. Only `*` is a wildcard; `[`, `]`, and `?` are treated literally. Patterns are **not** `${...}` templates and are not expanded.

Matching checks both:

- the whole annotation, and
- every nested subscript occurrence.

For example, `list[dict[str, Any]]` has two matched annotation texts: `list[dict[str, Any]]` and the nested `dict[str, Any]`. This means a pattern like `dict[str, Any]` can report the nested occurrence with the nested line/column.

Precedence is:

1. `allow`
2. explicit `forbid`
3. defaults

`allow` wins over both explicit `forbid` and defaults. An `allow` pattern can match either the offending nested occurrence or the root annotation text, so allowing `list[dict[str, Any]]` also allows the nested `dict[str, Any]` inside that root annotation.

Default rules flag string-keyed mappings whose value type is broad or union-shaped:

- mapping bases: `dict`, `Dict`, `Mapping`, `MutableMapping`, `OrderedDict`, `defaultdict` — including qualified forms such as `typing.Dict` and `collections.defaultdict`;
- key type: `str`;
- value type: `X | Y`, `Union[...]`, `Optional[...]`, `Any`, or `object`.

Default examples that are flagged:

```py
payload: dict[str, Any]
payload: dict[str, object]
payload: dict[str, str | list[str]]
payload: dict[str, Union[str, list[str]]]
payload: dict[str, Optional[str]]
payload: list[dict[str, Any]]
```

Default examples that are not flagged:

```py
payload: dict[str, str]
payload: Mapping[str, int]
payload: dict[int, Any]
payload: dict[str, list[str]]
```

Targets checked:

- function and method parameter annotations;
- function and method return annotations;
- module-level constants (`UPPER_CASE` assignments and `Final`-annotated assignments);
- class-body annotated attributes such as `payload: dict[str, Any]`.

For `publicOnly: true`, top-level symbols use normal export publicness (`__all__` when literal, otherwise no leading underscore). Class attributes are public only when their class is public and the attribute name does not start with `_`.

`restrictAnnotations` is only supported under `must`. Putting it under `mustNot` is rejected during config validation with:

```text
restrictAnnotations is only supported in "must", not "mustNot"; it already reports restricted annotations directly.
```

### `restrictRepeatedLiterals`

Flag repeated eligible string literals across the current matched scope.

```json
"must": { "restrictRepeatedLiterals": true }
```

The bare `true` form uses the default ratchet:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `minLength` | integer | `8` | Minimum decoded string length before a literal is considered. |
| `maxOccurrences` | integer | `2` | Maximum allowed occurrences of the same literal value in the effective scope. |
| `allow` | string[] | unset | Literal values to ignore. Patterns support `*`; `[`, `]`, and `?` are literal. |

Object form:

```json
"must": {
  "restrictRepeatedLiterals": {
    "minLength": 12,
    "maxOccurrences": 1,
    "allow": ["https://*"]
  }
}
```

Matching groups exact decoded Python string values across the whole effective scope of the convention or `must` block, after convention-level and block-level `excludeFiles` are applied. With a nested `for` block, the scope is the set of files produced by that block, not the parent `paths` file. Diagnostics are emitted only for occurrences in the currently evaluated file, so each repeated occurrence gets its own file/line/column diagnostic.

Eligible literals are standard-library `ast.Constant` string values. These are intentionally excluded:

- module, class, function, and method docstrings;
- bare string expression statements used as sentinels;
- f-string parts;
- empty strings;
- function parameter annotations, return annotations, and variable/class-body annotations;
- `TypeAlias` / PEP 695 type alias values;
- `__all__` assignment, augmentation, `append`, and `extend` values;
- common dunder tuple/list declarations such as `__slots__` and `__match_args__`;
- strings in `if __name__ == "__main__"` comparisons.

`restrictRepeatedLiterals` is cross-file and always evaluates the full selected scope. Under `--files`/`--changed`, scoping selects a convention when any file in the predicate's effective block scope is in scope; once selected, grouping still uses the full block scope.

`restrictRepeatedLiterals` is only supported under `must`. Putting it under `mustNot` is rejected during config validation.

### `restrictDuplicateFunctions`

Flag duplicate normalized function implementations across the current matched scope.

```json
"must": { "restrictDuplicateFunctions": true }
```

The bare `true` form uses the default ratchet:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `minStatements` | integer | `4` | Minimum normalized statement count before a function is considered. |
| `publicOnly` | boolean | `false` | When `true`, skip private top-level functions and private direct methods. |
| `allowNames` | string[] | unset | Function names, qualified names, or `file.py::qualified.name` labels to ignore. Patterns support `*`; `[`, `]`, and `?` are literal. |

Object form:

```json
"must": {
  "restrictDuplicateFunctions": {
    "minStatements": 6,
    "publicOnly": true,
    "allowNames": ["*_fixture", "tests/*::build_*"]
  }
}
```

Targets are top-level `def`/`async def` functions and direct methods inside top-level classes. Nested local functions and methods on nested classes are not collected as independent targets.

The fingerprint ignores function names, decorator lists, return annotations, parameter annotations, and source positions. It excludes the leading function docstring from the body. It preserves async-ness, parameter shape, literal constants, attributes, external/global names, nested function/class bodies, and a deterministic normalized form of local variable/parameter names. This means renamed local variables do not create distinct fingerprints, but calls to different external APIs do.

Functions are grouped by fingerprint across the whole effective scope of the convention or `must` block, after convention-level and block-level `excludeFiles` are applied. With a nested `for` block, the scope is the set of files produced by that block, not the parent `paths` file.

When a duplicate group is found, the canonical function is the lowest `(file_path, line, column, qualified_name)` occurrence. Diagnostics are emitted only for non-canonical duplicates in the currently evaluated file, with `found` set to `duplicate of <canonical_file>::<canonical_qualified_name>`.

`restrictDuplicateFunctions` is cross-file and always evaluates the full selected scope. Under `--files`/`--changed`, scoping selects a convention when any file in the predicate's effective block scope is in scope; once selected, grouping still uses the full block scope.

`restrictDuplicateFunctions` is only supported under `must`. Putting it under `mustNot` is rejected during config validation.

---

## Plugin predicates

Plugin predicates are custom predicate keys declared by installed Python distributions and enabled through top-level `plugins`.

```json
{
  "version": "v1",
  "plugins": ["acme-konpy-rules"],
  "conventions": [
    {
      "paths": "src/*.py",
      "must": {
        "requireMarker": "ACME_OK"
      },
      "mustNot": {
        "requireMarker": "DEBUG_ONLY"
      }
    }
  ]
}
```

Plugin predicate behavior is defined by the plugin descriptor:

- the predicate key;
- the pydantic value model;
- the handler;
- whether it needs AST structure;
- whether `mustNot` should split list values item-by-item;
- the forbidden message used by `mustNot`;
- whether placeholder validation should recursively scan plugin values.

Unknown plugin keys remain invalid unless a configured plugin distribution declares them. See [plugins.md](./plugins.md).

---

## Composing predicates

Multiple predicates in the same `must` are AND-ed:

```json
"must": {
  "haveType": "file",
  "export": ["create_service"],
  "exportTypes": ["ServiceConfig"],
  "importTypes": [{ "name": "ServiceBase", "from": "..base" }]
}
```

For OR-style logic (apply different predicates to different files), use [conditional rules](./conditional-rules.md) — the array form of `must` with `if`/`for` blocks.

Note that **reusable conventions** (those consumed via `conventionSources`) are restricted to flat object-form `must` and `mustNot` predicates — the `MustBlock[]` form is unavailable on the author side. Hand-written conventions in your own `konpy.json` can still use `MustBlock[]` in `must`. See [reusable-conventions.md](./reusable-conventions.md#restrictions).
