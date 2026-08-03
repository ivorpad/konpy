# AGENTS.md

konpy is a CLI linter that enforces structural conventions in Python codebases
from a declarative `konpy.json`. This repository dogfoods itself: `konpy.json`
is the baseline policy and `konpy.strict.json` extends it with the strict
policy. Source lives in `src/konpy/`, tests in `tests/`, user docs in `docs/`.
`tmp/konsistent` is a read-only reference clone of the upstream TypeScript
project; never modify it.

## Verification

Run this before considering any work complete:

```
uv run scripts/verify full
```

CI runs exactly this command, so a local pass is a CI pass. While iterating,
`uv run scripts/verify fast` checks only changed files. Releases go through
`scripts/verify release`.

Do not add `# konpy: ignore[...]` suppressions, edit the dogfood configs, or
relax a failing rule without explicit human approval. If a check disagrees
with your change, the check wins until a human says otherwise.

## Tool ownership

- Ruff owns lint.
- basedpyright owns type semantics.
- Import Linter owns resolved import architecture.
- konpy owns structural conventions: layout, required exports, module length,
  docstring and annotation coverage, duplication, unused code.
- pytest owns behavior.
- Packaging checks live in the `release` profile of `scripts/verify`.

Only these deterministic checks decide whether work passes. Model-backed
review can surface findings and propose rules, but a model verdict never
gates a write, a commit, or CI.

## Generated policy guidance

<!-- konpy:generated-guidance:start -->
<!-- Generated from konpy.strict.json by scripts/verify guidance --update. Do not edit by hand. -->
# Project conventions

Structural conventions enforced by `konpy`. Follow these before writing or editing Python files in this repository.

## Conventions

- **`packages-have-init`** (severity: `error`) — paths: `src/konpy/cli`, `src/konpy/config`, `src/konpy/core`, `src/konpy/predicates`, `src/konpy/python_ast`
  - Every konpy subpackage is a regular package.
  - must: `haveType` directory; `haveFiles` __init__.py
- **`predicate-modules-export-check`** (severity: `error`) — paths: `src/konpy/predicates/{module}.py`
  - Each predicate module exposes its check_<module> function.
  - excludes: `src/konpy/predicates/__init__.py`, `src/konpy/predicates/registry.py`, `src/konpy/predicates/_duplication_index.py`, `src/konpy/predicates/_handlers.py`, `src/konpy/predicates/_plugin.py`, `src/konpy/predicates/_restrict_annotations_matching.py`, `src/konpy/predicates/_utils.py`, `src/konpy/predicates/_wildcards.py`, `src/konpy/predicates/declaration_utils.py`, `src/konpy/predicates/import_.py`
  - must: `export` check_${module}
- **`init-files-are-barrels`** (severity: `error`) — paths: `src/konpy/**/__init__.py`
  - Package __init__.py files should only define the package public API through docstrings, imports, __all__, and re-export aliases.
  - hint: Move non-barrel logic (functions, classes, business logic) out of this __init__.py into a dedicated module and re-export it here instead.
  - must: `areBarrelFiles` true
- **`absolute-imports-only`** (severity: `error`) — paths: `src/konpy/**/*.py`, `!src/konpy/**/__init__.py`
  - Non-barrel Python modules should use absolute imports instead of relative imports.
  - hint: Rewrite relative imports (from . import x, from .. import y) as absolute imports rooted at the top-level package.
  - must not: `importFromCurrentDir` true; `importFromParents` true
- **`no-underscore-exports`** (severity: `error`) — paths: `src/konpy/**/*.py`
  - Modules should not list underscore-prefixed names in __all__.
  - hint: Drop the underscore-prefixed name from __all__, or rename it without the leading underscore if it's meant to be public.
  - must not: `matchContent` ^__all__\s*=\s*(?:\[[\s\S]*?["'](?!__[A-Za-z0-9_]+__["'])_[A-Za-z0-9_]+["']|\([\s\S]*?["'](?!__[A-Za-z0-9_]+__["'])_[A-Za-z0-9_]+["'])
- **`docstrings-on-public-api`** (severity: `error`) — paths: `src/konpy/**/*.py`, `!src/konpy/**/__init__.py`
  - Public classes and functions should have docstrings.
  - hint: Add a docstring explaining what this public class or function does, its parameters, and what it returns.
  - must: `haveDocstrings` {modules=false, classes=true, functions=true, publicOnly=true}
- **`annotated-public-functions`** (severity: `error`) — paths: `src/konpy/**/*.py`, `!src/konpy/**/__init__.py`
  - Public functions and methods should annotate parameters and return values.
  - hint: Add type annotations to this public function's parameters and return value.
  - must: `annotateFunctions` {returns=true, params=true, publicOnly=true}
- **`max-module-length`** (severity: `error`) — paths: `src/konpy/**/*.py`
  - Modules longer than 300 lines should be split.
  - must: `restrictFileLength` {maxLines=300}
- **`tests-never-skip`** (severity: `error`) — paths: `tests/**/*.py`, `!tests/e2e/fixtures/**`
  - Tests are deleted or fixed, never skipped; environment-conditional runs use skipif.
  - hint: Remove the skip/xfail marker and fix or delete the test, or use pytest.mark.skipif for a real environment condition.
  - must: `restrictDecorators` {forbid=pytest.mark.skip, pytest.mark.xfail}

## Unused code

- severity: `warning`
- included paths: `src/konpy/**/*.py`
- test paths: `**/tests/**`, `**/test_*.py`, `**/*_test.py`, `**/conftest.py`
- entrypoint files: `**/Dockerfile*`, `**/docker-compose*.yml`, `**/docker-compose*.yaml`, `**/template*.yml`, `**/template*.yaml`, `**/serverless*.yml`, `**/pyproject.toml`, `**/setup.py`, `**/setup.cfg`, `**/Makefile`
- registry decorator patterns treated as used: `field_validator`, `model_validator`, `computed_field`, `field_serializer`, `model_serializer`, `validator`, `root_validator`, `pytest.fixture`, `fixture`, `pytest.mark.*`, `app.*`, `router.*`, `blueprint.*`, `api.*`, `task`, `shared_task`, `celery.task`, `command`, `group`, `callback`, `app.command`, `app.callback`, `overload`, `typing.overload`, `singledispatch`, `functools.singledispatch`, `singledispatchmethod`, `register`, `*.register`
- hook / lifecycle names treated as used: `Config`, `main`, `model_config`, `model_fields`, `model_fields_set`, `model_post_init`, `setUp`, `setUpClass`, `setUpModule`, `setup_class`, `setup_function`, `setup_method`, `setup_module`, `tearDown`, `tearDownClass`, `tearDownModule`, `teardown_class`, `teardown_function`, `teardown_method`, `teardown_module`
- model base classes whose attributes count as used: `BaseModel`, `BaseSettings`, `Enum`, `IntEnum`, `NamedTuple`, `Protocol`, `StrEnum`, `TypedDict`, `enum.Enum`, `enum.IntEnum`, `enum.StrEnum`, `pydantic.BaseModel`, `pydantic_settings.BaseSettings`, `typing.NamedTuple`, `typing.Protocol`, `typing.TypedDict`, `typing_extensions.TypedDict`
- explicitly allowed dead-code names: _(none configured)_

## Suppressions

Suppression comments (`konpy: ignore[rule]`) are for approved exceptions only. Never add one without explicit human approval -- see `konpy docs suppressions`. Fix the violation, or ask a human to approve a suppression with a reason.
<!-- konpy:generated-guidance:end -->
