# Plugin predicates

Plugin predicates let installed Python packages add custom predicate keys to `must` and `mustNot`.

Plugins are **explicit opt-in only**. `konsistent` never auto-discovers or executes installed entry points unless the config names the distribution in top-level `plugins`.

## Enable plugins in config

```json
{
  "version": "v1",
  "plugins": ["acme-konsistent-rules"],
  "conventions": [
    {
      "name": "must-have-acme-marker",
      "paths": "src/*.py",
      "must": {
        "acmeMarker": "ACME_OK"
      }
    }
  ]
}
```

`plugins` is a list of installed Python distribution names. Names must match:

```text
[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]
```

Only entry points from those named distributions are loaded.

## Entry points

A plugin distribution exposes predicate descriptors through the `konsistent.predicates` entry-point group:

```toml
[project.entry-points."konsistent.predicates"]
acmeMarker = "acme_konsistent.rules:acme_marker"
```

Each entry point must load either:

- a `PredicatePlugin` instance, or
- a zero-argument callable returning a `PredicatePlugin`.

One entry point declares one predicate key.

## Public plugin API

Plugin authors should import from `konsistent.plugin`:

```py
from konsistent.plugin import PredicatePlugin, create_diagnostic
```

Available public imports:

- `PredicatePlugin`
- `PluginPredicateHandler`
- `PluginForbiddenMessageBuilder`
- `PredicateContext`
- `PyFileStructure`
- `Diagnostic`
- `DiagnosticSeverity`
- `create_diagnostic`

## Descriptor shape

```py
from __future__ import annotations

from typing import Literal

from konsistent.plugin import PredicatePlugin, create_diagnostic


def require_marker(
    *,
    expected: str,
    context,
    structure,
    convention_name=None,
    severity=None,
):
    source = context.file_system.read_file(context.path)
    if expected in source:
        return []

    return [
        create_diagnostic(
            file_path=context.path,
            predicate_name="requireMarker",
            message=f'Missing marker "{expected}"',
            convention_name=convention_name,
            severity=severity,
        )
    ]


plugin = PredicatePlugin(
    key="requireMarker",
    value_model=str,
    handler=require_marker,
    forbidden_message_template='Forbidden marker "{resolved_value}"',
)
```

Fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `key` | `str` | yes | Predicate key accepted in `must` / `mustNot`. Must not collide with built-ins or another loaded plugin. |
| `value_model` | pydantic-adaptable type | yes | Type or model used to validate the predicate value. Examples: `str`, `list[str]`, a `BaseModel`, or a `TypeAdapter`. |
| `handler` | callable | yes | Function that checks the predicate and returns diagnostics. |
| `forbidden_message_template` | `str` or callable | yes | Message used when the predicate appears in `mustNot` and the positive predicate passes. |
| `uses_ast` | `bool` | no, default `false` | If true, `structure` receives a parsed `PyFileStructure`. |
| `item_level_must_not` | `bool` | no, default `false` | If true and the value is a list, `mustNot` evaluates each item separately. |
| `validate_placeholders` | `bool` | no, default `true` | If true, strings inside the plugin value are checked for undeclared `${placeholder}` usage. |

## Handler contract

Handlers are called with keyword arguments:

```py
def handler(
    *,
    expected,
    context,
    structure,
    convention_name=None,
    severity=None,
) -> list[Diagnostic]:
    ...
```

| Argument | Description |
| --- | --- |
| `expected` | The validated predicate value from config. |
| `context` | `PredicateContext` for the matched path. Includes `path`, `placeholders`, `file_system`, `base_path`, `resolve_template()`, `file_exists()`, and `read_dir()`. |
| `structure` | `PyFileStructure` when `uses_ast=True`; otherwise `None` unless another predicate caused the file to be parsed for the same check. |
| `convention_name` | The active convention or block name, if available. |
| `severity` | The active severity (`"error"` or `"warning"`). |

Handlers do not receive a separate `file_system` argument. Use `context.file_system`, `context.file_exists()`, and `context.read_dir()`.

## Value validation

Plugin values are validated dynamically at config-load time using the descriptor's `value_model`.

```py
from pydantic import BaseModel


class RequireTextOptions(BaseModel):
    text: str
    case_sensitive: bool = True


plugin = PredicatePlugin(
    key="requireText",
    value_model=RequireTextOptions,
    handler=require_text,
    forbidden_message_template='Forbidden text "{value}"',
)
```

Then config may use:

```json
"must": {
  "requireText": {
    "text": "ACME_OK",
    "case_sensitive": false
  }
}
```

Unknown predicate keys remain invalid unless a named plugin distribution declares them.

## AST predicates

Set `uses_ast=True` when a plugin needs Python module structure:

```py
plugin = PredicatePlugin(
    key="declarePublicFactory",
    value_model=str,
    handler=declare_public_factory,
    forbidden_message_template='Forbidden factory "{resolved_value}"',
    uses_ast=True,
)
```

`structure` is a `PyFileStructure` containing parsed declarations, exports, imports, classes, functions, docstring targets, and annotation targets.

## `mustNot`

Plugin predicates automatically participate in `mustNot`.

```json
"mustNot": {
  "requireMarker": "DEBUG_ONLY"
}
```

`mustNot` runs the plugin handler as a normal positive predicate. If the handler returns no diagnostics, the path violated the negated rule and `konsistent` emits a `mustNot.<key>` diagnostic.

### Forbidden messages

String templates receive:

| Placeholder | Meaning |
| --- | --- |
| `{value}` | `str(expected)` |
| `{resolved_value}` | `context.resolve_template(expected)` when `expected` is a string, otherwise `str(expected)` |

```py
PredicatePlugin(
    key="requireMarker",
    value_model=str,
    handler=require_marker,
    forbidden_message_template='Forbidden marker "{resolved_value}"',
)
```

For more control, pass a callable:

```py
def forbidden_message(*, expected, context) -> str:
    return f'Forbidden marker "{context.resolve_template(expected)}"'

plugin = PredicatePlugin(
    key="requireMarker",
    value_model=str,
    handler=require_marker,
    forbidden_message_template=forbidden_message,
)
```

## Placeholder validation

By default, `konsistent` recursively scans string values inside plugin predicate values and reports undeclared `${placeholder}` references.

```json
{
  "paths": "src/{name}.py",
  "must": {
    "requireMarker": "${missing}"
  }
}
```

This fails before scanning:

```text
Convention "<name>" references "${missing}" in must.requireMarker, but neither paths nor placeholders declare "{missing}".
```

Set `validate_placeholders=False` when the plugin value uses strings that are not template-bearing config strings.

## Reusable conventions and inheritance

Reusable convention packages and inherited configs may contain plugin predicates, but the consuming config must opt into the plugin distribution through `plugins`.

Parent configs may also declare `plugins`. Plugin lists merge parent-first, then child, with duplicates removed by normalized distribution name.

```json
{
  "version": "v1",
  "extends": ["acme-base-config"],
  "plugins": ["team-extra-rules"],
  "conventions": []
}
```

If `acme-base-config` declares `plugins: ["acme-konsistent-rules"]`, the final runtime plugin order is:

```json
["acme-konsistent-rules", "team-extra-rules"]
```

## Loading rules

For each configured distribution name:

1. `konsistent` resolves it with `importlib.metadata.distribution(name)`.
2. It reads only that distribution's entry points.
3. It filters to group `konsistent.predicates`.
4. It loads each matching entry point.
5. Each entry point must produce a valid `PredicatePlugin`.
6. Predicate keys are merged into a per-run registry.

No global registry is mutated, and no entry point from an unlisted distribution is loaded.

## Error reference

| Condition | Error |
| --- | --- |
| Invalid distribution name | `Plugin "<name>": invalid Python distribution name. Plugin names must match [A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9].` |
| Distribution not installed | `Plugin "<name>": installed Python distribution not found. Install it or remove it from plugins.` |
| No predicate entry points | `Plugin "<name>": no entry points found in group "konsistent.predicates".` |
| Built-in key collision | `Plugin "<dist>" entry point "<entry_point>" declares predicate key "<key>", which conflicts with a built-in predicate. Choose a unique plugin predicate key.` |
| Plugin key collision | `Plugin "<dist>" entry point "<entry_point>" declares predicate key "<key>", which conflicts with plugin "<other_dist>" entry point "<other_entry_point>". Plugin predicate keys must be unique.` |

## JSON Schema note

The checked-in `konsistent.schema.json` includes the top-level `plugins` key, but it cannot statically enumerate predicate keys provided by arbitrary installed packages.

Plugin predicate keys are validated at runtime by `konsistent validate` and `konsistent check`.
