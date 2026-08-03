# Import boundaries: konpy vs. Import Linter

konpy's `importFrom` family and a tool like [Import Linter](https://import-linter.readthedocs.io/) both restrict what a module may import, but they answer different questions. Picking the wrong one gets you either a rule that silently misses a transitive violation, or a dependency you didn't need for a one-line check.

## konpy's import predicates: direct, source-level

`importFrom`, `importFromCurrentDir`, `importFromParents`, `importFromExternals`, and the `importTypes*` variants read the import statement in front of them, as written. No graph is built, nothing is resolved against `sys.path` or installed packages.

That gets you two things Import Linter can't:

- **Speed.** It's the same `ast.parse` pass konpy already runs for every other predicate — no separate graph build.
- **Works on broken or partial code.** A file with an unresolvable import, a module that doesn't exist yet, or a package that isn't installed still parses fine. Import Linter (via [Grimp](https://github.com/seddonym/grimp)) has to import-resolve every module in scope, so it needs a working, importable package.

The cost is exactly what "source-level" implies: `mustNot: { "importFrom": "acme.internal" }` catches `from acme.internal import x` directly in the matched file. It does not catch a file that imports `acme.public`, where `acme.public` itself imports `acme.internal` — konpy never looks past the one import statement it's checking. See [Predicates: Import predicates](../reference/predicates.md#import-predicates) for the full semantics of each variant.

`importFrom` also only sees module-level imports. `restrictImports` is the scope-aware variant: it collects imports at any scope, including ones nested inside a function body, so it catches an SDK import hidden behind a `def` where `importFrom` on the same file would report nothing. That closes the gap that used to need a `matchContent` regex like `(?m)^\s*(from|import)\s+...` as a workaround — that recipe is no longer necessary. `restrictImports` is still source-level like everything else in this section: no graph, no resolution against installed packages, so the Import Linter guidance below still applies wherever you need transitive or resolved-graph guarantees. See [`restrictImports`](../reference/predicates.md#restrictimports) for the full option set.

## Import Linter: resolved-graph contracts

Import Linter builds the real import graph for an installed, importable package and checks contracts against it:

- **`forbidden`** — module A must never import module B, directly or transitively.
- **`layers`** — a stack of layers where a lower layer can never import a higher one, checked across the whole graph.
- **`independence`** — a set of modules must share no import path between them.

Reach for it when the rule is actually about the *resolved* dependency graph — "domain never depends on infrastructure, no matter how many modules the import passes through" — or about package identity rather than specifier text ("this is the same module whether imported as `pkg.mod` or via a re-export"). It requires the package to be importable, so it can't run against a fragment or a file mid-refactor the way a konpy predicate can.

## When custom Grimp analysis is warranted

Import Linter's contract types cover forbidden/layers/independence queries over the import graph. If your rule is a graph query none of those three express — something Import Linter's contract API has no shape for, not just something that needs more config — that's when writing directly against [Grimp](https://github.com/seddonym/grimp) (the graph library Import Linter is built on) is warranted. Check the contract types first; most "we need custom graph logic" requests turn out to be `layers` or `independence` with the right module list.

## Worked example: this repo's own contracts

konpy's own `pyproject.toml` uses two `forbidden` contracts to keep the engine layers independent of the CLI, and to keep the AST layer dependency-free:

```toml
[tool.importlinter]
root_package = "konpy"

[[tool.importlinter.contracts]]
name = "engine layers never import the CLI"
type = "forbidden"
source_modules = [
    "konpy.core",
    "konpy.config",
    "konpy.python_ast",
    "konpy.predicates",
    "konpy.unused",
    "konpy.infer",
    "konpy.plugin",
]
forbidden_modules = ["konpy.cli"]

[[tool.importlinter.contracts]]
name = "python_ast stays dependency-free"
type = "forbidden"
source_modules = ["konpy.python_ast"]
forbidden_modules = [
    "konpy.cli",
    "konpy.config",
    "konpy.core",
    "konpy.predicates",
    "konpy.unused",
    "konpy.infer",
    "konpy.plugin",
]
```

Both are transitive: the first fails if any engine-layer module imports `konpy.cli`, even three hops deep through a module that itself only imports something that imports `konpy.cli`. A source-level `importFrom` predicate could catch the direct case, but not a violation introduced by refactoring an intermediate module. `lint-imports` runs as its own step in `scripts/verify full`, alongside `konpy check`, not as a konpy convention.

## See also

- [Predicates: Import predicates](../reference/predicates.md#import-predicates)
- [Reusable packs: `hexagonal-architecture.json`](../reference/packs.md#hexagonal-architecturejson)
