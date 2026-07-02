# Reusable packs

The repo ships three off-the-shelf convention packs under [`packs/`](../../packs/). Each is a `ReusableConventionsPackageV1` (`conventionSpecVersion: "v1"`) that you bind via `conventionSources` and reference by `<alias>/<name>` — see [Reusable conventions](./reusable-conventions.md) for the general mechanism. This page documents what each pack's conventions check, the layout each one assumes, and every convention's `hint`.

Packs are **off-the-shelf**: if your layout doesn't match a pack's assumptions, use the matching section in [Templates](../guides/templates.md) to hand-write an equivalent convention with your own paths instead of fighting the pack's placeholders.

## `python-best-practices.json`

General Python structural hygiene, layout-independent (paths use `**` globs, not a fixed directory shape). See [Authoring reusable conventions](../guides/authoring-reusable-conventions.md) for how to consume individual rules with `use` overrides.

| Convention | Checks | Hint |
| --- | --- | --- |
| `init-files-are-barrels` | Every `__init__.py` is a barrel file (docstring, imports, `__all__`, re-export aliases only — no other logic). | Move non-barrel logic out of the `__init__.py` into a dedicated module and re-export it. |
| `absolute-imports-only` | Non-`__init__.py` modules use absolute imports, never `from .` / `from ..`. | Rewrite relative imports as absolute imports rooted at the top-level package. |
| `no-underscore-exports` | `__all__` never lists an underscore-prefixed name. | Drop the underscore-prefixed name from `__all__`, or rename it without the leading underscore. |
| `class-name-matches-filename` | A `*_service.py` module exports a `${name.toPascalCase()}Service` class. | Export a PascalCase `Service` class named after the file's stem. |
| `exported-constants-are-upper-case` | A constant module exports `${name.toConstantCase()}`. | Export a `CONSTANT_CASE` constant named after the file. |
| `docstrings-on-public-api` | Public classes and functions have docstrings. | Add a docstring explaining what the class/function does, its parameters, and its return value. |
| `annotated-public-functions` | Public functions/methods annotate parameters and return values. | Add type annotations to the function's parameters and return value. |
| `paired-test-files` | Top-level `src/{name}.py` has a matching `tests/test_{name}.py`. | Add a `tests/test_<module>.py` covering the module's public behavior. |
| `no-todo-comments` | No `TODO`/`FIXME`/`XXX` markers in source. | Remove the marker and file a tracked issue for the remaining work. |
| `public-api-modules-declare-all` | Non-`__init__.py` modules under `src/**` declare `__all__` explicitly. | Add an explicit `__all__` list naming the module's public names. |
| `package-inits-have-docstrings` | Every `__init__.py` has a module docstring. | Add a module docstring summarizing what the package exposes and why. |
| `component-packages-have-readme` | Each top-level directory under `packages/` has a `README.md`. | Add a `README.md` describing the package's purpose, ownership, and usage. |

## `hexagonal-architecture.json`

Ports-and-adapters (hexagonal) layering. Assumes a single-package layout with `src/domain/`, `src/ports/`, `src/adapters/`, and `src/use_cases/` directories, plus `tests/use_cases/` for use-case tests. If your project splits into multiple packages or nests these directories differently, adapt the paths with the `use` object form or write the equivalent rule from scratch (see [Templates § Layered import-direction bans](../guides/templates.md#layered-import-direction-bans) and [§ DDD package layout](../guides/templates.md#ddd-package-layout)).

| Convention | Checks | Hint |
| --- | --- | --- |
| `domain-does-not-import-adapters-or-infrastructure` | `src/domain/**/*.py` never imports anything from an `adapters` or `infrastructure` package. | Move the framework-specific logic behind a port and inject it into the domain, instead of importing adapters/infrastructure directly. |
| `ports-are-protocols-or-abcs` | `src/ports/**/*.py` (excluding `__init__.py`) defines a class extending `Protocol` or `ABC`. | Define the port as a `typing.Protocol` or `abc.ABC` subclass so adapters can be swapped without changing the domain. |
| `adapters-export-adapter-suffix` | `src/adapters/**/*.py` (excluding `__init__.py`) defines a class whose name ends in `Adapter`. | Name the implementing class with an `Adapter` suffix (e.g. `PostgresOrderRepositoryAdapter`). |
| `use-cases-paired-with-tests` | Every `src/use_cases/{name}.py` has a matching `tests/use_cases/test_{name}.py`. | Add a `tests/use_cases/test_<name>.py` covering the use case's application logic. |

Fixtures demonstrating both the clean and violating shape live at `tests/e2e/fixtures/hexagonal-architecture-pack/` and `tests/e2e/fixtures/hexagonal-architecture-pack-broken/`.

## `src-layout.json`

`src/` layout hygiene and test mirroring. Assumes the conventional `src/`-root layout: `pyproject.toml` and `src/` at the project root, one or two levels of packages under `src/`, and a `tests/` tree that mirrors `src/`'s shape one-to-one.

| Convention | Checks | Hint |
| --- | --- | --- |
| `project-root-uses-src-layout` | The project root is a directory containing both `pyproject.toml` and `src`. | Move importable code into a `src/` directory and keep `pyproject.toml` at the project root. |
| `top-level-src-packages-have-init` | Each top-level directory under `src/` contains an `__init__.py`. | Add an `__init__.py` to the directory so it's importable as a package. |
| `top-level-modules-mirror-into-tests` | Every top-level `src/{name}.py` (excluding `src/__init__.py`) has a matching `tests/test_{name}.py`. | Add a `tests/test_<module>.py` covering the module's public behavior. |
| `nested-modules-mirror-into-tests` | Every `src/{package}/{name}.py` one level deep (excluding `__init__.py` files) has a matching `tests/{package}/test_{name}.py`. | Add a `tests/<package>/test_<module>.py` mirroring the module's location under `src/`. |

Fixtures: `tests/e2e/fixtures/src-layout-pack/` (clean) and `tests/e2e/fixtures/src-layout-pack-broken/` (violating).

## Consuming a pack

Bind it through `conventionSources`, then reference rules by name (string form uses the pack's own `paths`; object `use` form lets you override `paths`/`placeholders`/`severity`):

```json
{
  "version": "v1",
  "conventionSources": {
    "hex": "./packs/hexagonal-architecture.json",
    "layout": "./packs/src-layout.json"
  },
  "conventions": [
    "hex/domain-does-not-import-adapters-or-infrastructure",
    "hex/ports-are-protocols-or-abcs",
    "hex/adapters-export-adapter-suffix",
    "hex/use-cases-paired-with-tests",
    "layout/project-root-uses-src-layout",
    "layout/top-level-src-packages-have-init",
    "layout/top-level-modules-mirror-into-tests",
    "layout/nested-modules-mirror-into-tests"
  ]
}
```

Packs can also be published on PyPI and consumed by distribution name — see [README § Distributing packs on PyPI](../../README.md#distributing-packs-on-pypi) and [Reusable conventions](./reusable-conventions.md).
