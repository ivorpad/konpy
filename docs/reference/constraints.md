# Constraints

Constraints filter which placeholder values a rule applies to. They appear in two places:

1. **Inline path constraints** — `paths: "packages/{providerId:matches(^[a-z]+ai$)}"`. Captured paths whose value fails the constraint are skipped.
2. **`if.placeholderSatisfies`** — gates a `must` block on the placeholder's value (see [conditional-rules.md](./conditional-rules.md)).

Both contexts use the same `name:constraint(arg)` syntax.

## Catalog

| Constraint | Description |
| --- | --- |
| [`matches(regex)`](#matchesregex) | Placeholder value must match the regex. |
| [`segments(n)`](#segmentsn) | Placeholder value must have exactly `n` word segments. |

## `matches(regex)`

The placeholder value must match the regex, compiled with Python's [`re`](https://docs.python.org/3/library/re.html) module. Case-sensitive. The pattern is unanchored (`re.search`) unless you anchor it explicitly with `^` and `$`.

### Inline path constraint

```json
{
  "paths": "packages/{providerId:matches(^[a-z]+ai$)}/src/${providerId}_stem.py",
  "must": {
    "exportConstants": ["${providerId.extract(^([a-z]+)ai$)}"]
  }
}
```

Only providers whose ID ends in `ai` (e.g., `openai`, `mistralai`) are considered. The rule does not apply to `google`, `anthropic`, etc.

### `if.placeholderSatisfies`

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

The base rule (`src/__init__.py` required) applies to every package. The conditional block (`src/${providerId}_stem.py` required) applies only when `providerId` matches the regex.

### Divergence from JS RegExp

The original TypeScript `konsistent` compiled `matches`/`extract` patterns as JavaScript `RegExp`. The Python port uses Python `re`, so a few syntaxes differ. For simple character classes and anchors the behavior is identical, but note:

- **Named groups** use `(?P<name>...)` (Python), not `(?<name>...)` (JS). Backreferences are `(?P=name)`.
- **Inline flags** must appear at the **start** of the pattern in current Python versions — `(?i)abc`, not `abc(?i)`. A mid-pattern global flag raises an error and makes the constraint fail.
- **`\d`, `\w`, `\s`** are **Unicode-aware** by default on `str` patterns. Restrict to ASCII with `(?a)` at the start of the pattern if you need JS-style ASCII-only classes.

An invalid pattern makes the constraint evaluate to `false` (the path is skipped / the block does not run) rather than crashing.

## `segments(n)`

The placeholder value must split into exactly `n` word segments. Splitting is on `-`, `_`, or camelCase boundaries.

```
chat                    → 1 segment
chat-language           → 2 segments
chat-language-model     → 3 segments
chatLanguage            → 2 segments
chat_language           → 2 segments
```

### Inline use

```json
{
  "paths": "packages/{providerId}",
  "must": [
    {
      "for": {
        "files": "*/${providerId}_{modelKind:segments(2)}_model.py"
      },
      "must": {
        "exportFunctions": [
          "create_${providerId}_${modelKind.toNthSegment(1)}_model_${modelKind.toNthSegment(0)}"
        ]
      }
    },
    {
      "for": {
        "files": "*/${providerId}_{modelKind:segments(1)}_model.py"
      },
      "must": {
        "export": [
          "${providerId.toPascalCase()}${modelKind.toPascalCase()}ModelConfig"
        ]
      }
    }
  ]
}
```

The first block matches files like `chat-language_model.py` (2-segment `modelKind`); the second matches `embedding_model.py` (1-segment `modelKind`). Different `must` predicates apply to each shape.

### `if.placeholderSatisfies`

```json
{
  "if": { "placeholderSatisfies": "modelKind:segments(2)" },
  "must": { "exportTypes": ["${modelKind.toPascalCase()}Config"] }
}
```

## Syntax notes

- The argument inside `(...)` is taken **verbatim** — no quotes around regexes or numbers.
- The argument may **not contain `}`**. If you need a regex quantifier, use repetition: `\d\d?` instead of `\d{1,2}`.
- Constraints apply to placeholder **values** (`{...}`) and to `placeholderSatisfies` arguments. They do not apply to template substitutions (`${...}`).
- An `if` block has exactly one of `hasFile` or `placeholderSatisfies` (see [conditional-rules.md](./conditional-rules.md)).
- `segments(n)` splits on `-`, `_`, and camelCase boundaries. The `toNthSegment*` template helpers split on `-` only — see [path-patterns.md](./path-patterns.md#case-transformations).

## Difference from path negation

[Path negation](./path-patterns.md#negation) (`"!packages/test-utils"`) excludes specific paths after they've been matched by other entries. Constraints operate on the captured value of a placeholder — they let you express "match every package whose name follows this shape" without enumerating exceptions.

Use constraints when the rule applies to a class of placeholders (e.g., "all AI providers"); use negation when the rule has a small list of literal exceptions.
