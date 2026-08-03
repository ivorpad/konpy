# Reusable packs

The repository ships reusable structural convention packs under [`packs/`](../../packs/). Each is a `ReusableConventionsPackageV1` loaded through `conventionSources`.

If a rule needs one-file judgment rather than a structural predicate, use a [semantic-rules package](./semantic-rules.md) instead. Semantic rules are consumed by `konpy review --rules`, not `konpy.json`.

## `python-best-practices.json`

General Python structural checks.

| Convention | Checks | Hint |
| --- | --- | --- |
| `init-files-are-barrels` | `__init__.py` files contain barrel content only | Move logic into a module and re-export it |
| `absolute-imports-only` | Non-init modules avoid relative imports | Rewrite imports from the top-level package |
| `no-underscore-exports` | `__all__` excludes private names | Remove or rename the export |
| `class-name-matches-filename` | Service modules export a matching service class | Match the class name to the filename |
| `exported-constants-are-upper-case` | Constant modules export a matching constant | Use constant case |
| `docstrings-on-public-api` | Public classes and functions have docstrings | Add a description of behavior |
| `annotated-public-functions` | Public functions have parameter and return annotations | Add missing annotations |
| `paired-test-files` | Source modules have paired test files | Add the matching test file |
| `no-todo-comments` | Source excludes TODO-style markers | Track work outside source comments |
| `public-api-modules-declare-all` | Public modules declare `__all__` | Add the public names |
| `package-inits-have-docstrings` | Package init files have module docstrings | Describe the package |
| `component-packages-have-readme` | Component directories contain a README | Document purpose and usage |

## `typed-records.json`

Typed-record annotation checks.

| Convention | Checks | Hint |
| --- | --- | --- |
| `no-anonymous-record-annotations` | Public annotations avoid identity-less mappings such as `dict[str, Any]` | Define a named model, `TypedDict`, or dataclass |

## `no-duplication.json`

Cross-file duplication ratchets.

| Convention | Checks | Hint |
| --- | --- | --- |
| `no-repeated-string-literals` | Eligible string literals do not exceed the configured repetition threshold | Extract a shared constant or fixture |
| `no-duplicate-functions` | Functions and methods do not repeat the same normalized implementation | Extract shared behavior |

These rules ship at warning severity for incremental adoption.

## `hexagonal-architecture.json`

Assumes:

```text
src/domain/
src/ports/
src/adapters/
src/use_cases/
tests/use_cases/
```

| Convention | Checks | Hint |
| --- | --- | --- |
| `domain-does-not-import-adapters-or-infrastructure` | Domain modules avoid adapter and infrastructure imports | Move integration logic behind a port |
| `ports-are-protocols-or-abcs` | Port modules define `Protocol` or `ABC` classes | Define the boundary explicitly |
| `adapters-export-adapter-suffix` | Adapter modules define `*Adapter` classes | Use the adapter suffix |
| `use-cases-paired-with-tests` | Use cases have paired tests | Add the corresponding test |

`domain-does-not-import-adapters-or-infrastructure` is a `matchContent` check on each domain file's own source text: it catches a domain module that imports `adapters`/`infrastructure` directly, not one that imports a third domain module that does. It's a direct, source-level check, not a resolved-graph one. For a contract that follows the import chain, use Import Linter — see [Import boundaries](../guides/import-boundaries.md).

## `src-layout.json`

Assumes a standard `src/` layout with mirrored tests.

| Convention | Checks | Hint |
| --- | --- | --- |
| `project-root-uses-src-layout` | Root contains `pyproject.toml` and `src` | Move importable code under `src` |
| `top-level-src-packages-have-init` | Top-level packages contain `__init__.py` | Add the package initializer |
| `top-level-modules-mirror-into-tests` | Flat modules have matching tests | Add `tests/test_<name>.py` |
| `nested-modules-mirror-into-tests` | One-level nested modules have mirrored tests | Mirror the package path under `tests` |

## Consuming a pack

Bind pack files to local prefixes:

```json
{
  "version": "v1",
  "conventionSources": {
    "bp": "./packs/python-best-practices.json",
    "hex": "./packs/hexagonal-architecture.json",
    "layout": "./packs/src-layout.json"
  },
  "conventions": [
    "bp/docstrings-on-public-api",
    "hex/domain-does-not-import-adapters-or-infrastructure",
    "layout/project-root-uses-src-layout"
  ]
}
```

Use object form to override paths or severity:

```json
{
  "use": "bp/paired-test-files",
  "paths": [
    "src/{name}.py",
    "!src/__init__.py"
  ]
}
```

Installed Python distributions may also supply reusable packages. See [Reusable conventions](./reusable-conventions.md).

## When a pack is not enough

Use the cheapest suitable mechanism:

1. a shipped convention;
2. a hand-written convention using built-in predicates;
3. a reusable package;
4. a semantic rule for one-file judgment;
5. a plugin predicate for deterministic custom logic.

Do not use `matchContent` to imitate an established Ruff or mypy rule.

## See also

- [Reusable conventions](./reusable-conventions.md)
- [Semantic rules](./semantic-rules.md)
- [Templates](../guides/templates.md)
- [Extracting rules](../guides/extracting-rules.md)
