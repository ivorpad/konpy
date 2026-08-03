# CI integration

`konpy` is designed to run as part of CI. This guide covers GitHub Actions setup. For commands, flags, output formats, and exit codes, see [cli.md](../reference/cli.md).

## GitHub Actions

`konpy` auto-detects GitHub Actions via `GITHUB_ACTIONS=true` and switches to the [`github` output format](../reference/cli.md#output-formats), emitting `::error` and `::warning` annotations automatically. No flags needed:

```yaml
name: konpy

on:
  pull_request:
  push:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen
      - run: uv run konpy check
```

Violations appear inline on the PR diff as `::error` or `::warning` annotations. Errors fail the job; warnings do not (unless [`--error-on-warnings`](../reference/cli.md#flags) is set).

## Posting violations as a PR comment

Combine `--format=markdown` with the GitHub CLI:

```yaml
- name: Run konpy
  run: uv run konpy check --format=markdown > konpy-report.md || true

- name: Comment on PR
  if: github.event_name == 'pull_request'
  run: gh pr comment ${{ github.event.pull_request.number }} -F konpy-report.md
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

The `|| true` keeps the comment step running even when `konpy` exits non-zero. Add a separate step that re-runs `konpy` (without the redirect) to restore the failure exit code.

## Strict CI flags

For stricter pipelines, see the [flags reference](../reference/cli.md#flags). The CI-relevant ones:

- `--error-on-warnings` — fail the build on warnings as well as errors.
- `--diagnostic-level error` — skip warning-severity conventions entirely (faster than evaluating and filtering).
- `--max-diagnostics=<n>` — raise the default cap of 100 if your codebase produces more violations during initial adoption.

## Failing fast on config errors

Run `validate` before `check` in CI to surface config errors clearly (separate red flag from convention violations):

```yaml
- run: uv run konpy validate
- run: uv run konpy check
```

See [`validate`](../reference/cli.md#validate) for the success/failure semantics.

## Combining with other checks

`konpy` is structural — it does not replace lint, format, type, or test checks. A typical CI job:

```yaml
- run: uv sync --frozen
- run: uv run mypy .
- run: uv run pytest
- run: uv run ruff check      # lint + format
- run: uv run konpy check
```

Run `konpy` after the lighter checks so structural failures surface against a known-good baseline. For custom reports, gating, or agent workflows, use [`--format=json`](../reference/cli.md#json) and group results by `conventionName` — see [fixing-violations.md](./fixing-violations.md).

## One verification entry point

As that job grows, put it behind one script your repository owns instead of listing commands separately in CI, pre-commit, and any Claude Code hooks:

```bash
#!/usr/bin/env bash
# scripts/verify
set -euo pipefail
uv run mypy .
uv run pytest
uv run ruff check
uv run konpy check
```

```yaml
- run: uv sync --frozen
- run: uv run scripts/verify
```

`konpy` is one step in that script, not the whole of it: a linter alongside your type checker and test suite, not a replacement for CI. The payoff is that CI, a local pre-push check, and a [`PreToolUse`/`PostToolUse` hook](./claude-code-hook.md) all call the same entry point. Add a flag to the `konpy check` line (`--error-on-warnings`, a stricter `--diagnostic-level`) and every caller picks it up without editing three separate command lists.

### Or: declare the roster in `konpy.json` with `konpy verify`

A bespoke `scripts/verify` still has to be written and maintained as its own file. [`konpy verify`](../reference/cli.md#verify) gets you the same one-entry-point property without one: the step roster lives in `konpy.json` itself, next to your conventions, instead of in a separate script.

```json
{
  "version": "v1",
  "conventions": [],
  "verify": {
    "steps": [
      { "name": "ruff", "run": ["ruff", "check"] },
      { "name": "konpy-check", "run": ["konpy", "check"] },
      { "name": "pytest", "run": ["pytest", "-q"] }
    ]
  }
}
```

```yaml
- run: uv sync --frozen
- run: uv run konpy verify
```

Every step always runs, even after an earlier one fails, so one CI job reports everything that's broken instead of stopping at the first red step. A missing tool (`ruff` not installed, say) is a step *failure*, not a silent skip — `pip install "konpy[quality]"` covers `ruff`/`basedpyright`/`import-linter` if your roster calls them and CI doesn't already provide them. See [`verify`](../reference/cli.md#verify) for the full config shape and exit-code contract.
