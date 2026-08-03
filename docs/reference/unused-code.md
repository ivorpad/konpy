# Unused-code detection

The optional `unusedCode` block turns on a **classifier** for unreferenced
definitions. Unlike `vulture` or `basedpyright`'s `reportUnusedFunction`, it does
not flag every unreferenced name — it classifies each definition and reports only
the two actionable classes (`dead`, `test-only`), staying silent on the
systematic false-positive classes that framework code produces (decorator-
registered handlers, lifecycle hooks, model fields, entrypoint-referenced
symbols). The design goal is **zero noise**: it under-reports before it ever
reports something that is actually used.

It reuses the config layer, the filesystem/path matcher, and the standard-library
`ast` module. No new dependencies.

## Enabling it

Add an `unusedCode` object to `konpy.json`. A bare `{}` is already
low-noise thanks to shipped framework presets:

```json
{
  "version": "v1",
  "conventions": [],
  "unusedCode": {}
}
```

`unusedCode` runs in addition to your conventions. It does not change
`files_checked` (that stays the count of convention-checked paths); it only adds
diagnostics. Diagnostics default to `warning` severity, so `check` exits 0 unless
you pass `--error-on-warnings`. With `--diagnostic-level error` the rule is
skipped entirely when its severity resolves to `warning`.

## Taxonomy

Every collected definition (module-level function, class, constant, and one
level of class-body methods and attributes) is classified in priority order:

| Class | Meaning | Result |
|---|---|---|
| `allowed` | name or qualname is in `allow` | silent |
| `hook` | dunder (`__x__`) or a framework lifecycle name (`model_post_init`, `setUp`, `main`, …) | silent |
| `registered` | bears a registry decorator (`@app.*`, `@field_validator`, `@pytest.fixture`, …) | silent |
| `model-field` | class attribute on a model base (`BaseModel`, `BaseSettings`, `TypedDict`, `Enum`, …) or `@dataclass` class — including bases reached through an intermediate class defined in the same module (`Child(Base)` where `Base(TypedDict)`); an intermediate base imported from another module is not resolved | silent |
| `protocol-override` | public method on a class whose base is imported from a third-party (non-stdlib, non-repo) module — the library dispatches to it by name, so a zero reference count says nothing; private `_`-methods stay reportable | silent |
| `entrypoint` | name appears as a string token in a declared entrypoint file (Dockerfile `CMD`, SAM/serverless templates, `pyproject.toml`, …) | silent |
| `dead` | no reference anywhere (code, tests, entrypoint files, strings) | **report** (`unusedCode.dead`) |
| `test-only` | referenced only under test globs | **report** (`unusedCode.testOnly`) |
| `used` | referenced by production code | silent |

Reference resolution counts `ast.Name` loads/stores, `ast.Attribute` `.attr`
accesses, import alias names, and identifier-like tokens (>= 2 chars) inside
string literals — the last catches `"src.module.handler"` and `getattr` strings.
Keyword-argument *names* do not count. A definition's own binding occurrence is
excluded so a never-used constant does not reference itself.

## Config keys

All keys are optional. User values **extend** (union with) the presets, except
`allow`, which is standalone.

| Key | Type | Default | Purpose |
|---|---|---|---|
| `include` | `string[]` | `["**/*.py"]` (minus `testGlobs`) | Production Python files that define symbols and contribute references. |
| `testGlobs` | `string[]` | `["**/tests/**", "**/test_*.py", "**/*_test.py", "**/conftest.py"]` | Files whose references count as *test* references. Defaults are recursive: nested test dirs (`e2e-tests/`, `pkg/tests/`) count too. |
| `entrypointFiles` | `string[]` | `**/Dockerfile*`, `**/docker-compose*.{yml,yaml}`, `**/template*.{yml,yaml}`, `**/serverless*.yml`, `**/pyproject.toml`, `**/setup.py`, `**/setup.cfg`, `**/Makefile` | Non-Python files tokenized for entrypoint references, at any depth (console scripts in `examples/*/pyproject.toml` count). |
| `registryDecorators` | `string[]` | framework presets | fnmatch-style patterns matched against a decorator's dotted name (call parens stripped): `app.*` matches `app.get`. |
| `hookNames` | `string[]` | framework presets | Method/attribute names treated as lifecycle hooks. Dunders are always hooks. |
| `modelBases` | `string[]` | framework presets | Base-class names whose attributes are model fields. A dataclass decorator listed here is also honored. |
| `allow` | `string[]` | `[]` | Escape hatch: silences a definition by `name` or `qualname`. |
| `severity` | `"error" \| "warning"` | `"warning"` | Diagnostic severity for both `unusedCode.dead` and `unusedCode.testOnly`. |

Defaults are applied by the engine, not by the config schema, so an explicitly
provided key fully replaces its default while presets are still unioned in.

## Presets

Shipped so `"unusedCode": {}` already understands common frameworks:

- **Registry decorators**: pydantic (`field_validator`, `model_validator`,
  `computed_field`, `field_serializer`, `model_serializer`, `validator`,
  `root_validator`), pytest (`pytest.fixture`, `fixture`, `pytest.mark.*`),
  FastAPI/Flask/Django/Powertools resolvers (`app.*`, `router.*`, `blueprint.*`,
  `api.*`), celery (`task`, `shared_task`, `celery.task`), click/typer
  (`command`, `group`, `callback`, `app.command`, `app.callback`), and
  dispatch/overload helpers (`overload`, `singledispatch`, `*.register`).
- **Hook names**: all dunders, pydantic hooks (`model_post_init`, `model_config`,
  `Config`, `model_fields_set`, `model_fields`), unittest/pytest lifecycle
  (`setUp`/`tearDown`/`setUpClass`/…, `setup_method`/`teardown_method`/…), and
  `main`. `handler` is *not* a preset — it is project-specific; declare it in
  `hookNames` or rely on entrypoint-file detection.
- **Model bases**: `BaseModel`, `pydantic.BaseModel`, `BaseSettings`,
  `pydantic_settings.BaseSettings`, `TypedDict`, `Protocol`, `NamedTuple`,
  `Enum`/`StrEnum`/`IntEnum`, plus `@dataclass` decorator detection.

## Limitations

- **Name-based matching.** References are resolved by bare name, so two
  definitions that share a name share references. This under-reports (a truly
  dead `A.process` is spared if any `process` is used) but never produces a false
  positive.
- **No dynamic resolution.** `getattr` chains, `entry_points` plugin discovery
  beyond declared entrypoint files, and reflection are not followed (string
  tokens inside literals are the only dynamic signal).
- **Single-package scope.** Cross-package analysis is out of scope; a symbol used
  only by an external consumer looks dead unless referenced in an entrypoint file
  or listed in `allow`.
- **Self-reference caveat.** A definition whose only reference is its own
  `__all__` listing in the same module counts as used — an intentional trade-off
  that keeps noise at zero.
- **Scope depth.** Nested functions inside functions and local variables are not
  collected (v1).

## Precision posture

False positives are treated as defects. A definition classified `dead` or
`test-only` that is actually referenced from production code is a bug, fixed
by tightening the classifier or adding a preset, not worked around by asking
users to list more names in `allow`. False negatives are the accepted cost of
holding that line: bare-name matching, string-token references, and framework
exemptions all trade completeness for the zero-false-positive guarantee.

`test-only` is a deliberately separate signal, not a bug class. A definition
referenced only under a test glob is a distinct finding (dead test scaffolding,
or production code that only a test still calls) from `dead` (referenced
nowhere at all). Neither classification means "the detector missed a
reference"; it means the reference it found lives in a specific place.

Use in a library cannot be inferred from one repository. A public function
with zero references inside this codebase may still be load-bearing for
external consumers this scan never sees. `entrypointFiles`, `allow`, and the
`protocol-override`/`registered`/`hook` classes exist to keep that gap from
producing noise, but they cannot enumerate every external caller. When a
`dead` finding is genuinely public API, put it in `allow`; do not delete it on
the classifier's say-so.

Framework exemptions (registry decorators, hook names, model bases) are part
of the compatibility surface, not incidental detail. Narrowing or removing one
without evidence that a framework changed its dispatch mechanism reintroduces
false positives across every project relying on that preset.

### Evaluation harness

`scripts/eval_unused [path]` runs this engine over a target directory and,
when `vulture` is reachable via `uvx`, also runs vulture
(`--min-confidence 80`) over the same path, printing a best-effort overlap
keyed on `(file, symbol name)`. It exists to eyeball agreement between the two
detectors during development. It has no pass/fail verdict, is not a test, and
is never invoked by `scripts/verify` or CI.
