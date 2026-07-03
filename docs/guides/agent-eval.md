# Agent evaluation harness

`scripts/eval_conventions.py` lets you A/B-compare how much structural drift a coding agent introduces or removes under different guidance strategies, using konsistent's own diagnostics as the metric. It runs `konsistent check --format json` against a target repo and reduces the result into a stable, diffable metrics summary you can snapshot before and after an agent run.

## What it measures

Each `run` invocation produces a JSON metrics summary with:

- **`summary`** — top-line counts: files checked, total diagnostics, errors, warnings, suppressed, and konsistent's own reported duration.
- **`bySeverity`** — diagnostic counts grouped by `error`/`warning`.
- **`byConvention`** — diagnostic counts grouped by convention name (diagnostics with no `conventionName` are bucketed under `"(none)"`).
- **`byPredicate`** — diagnostic counts grouped by predicate name (e.g. `haveType`, `mustNot.import`, `unusedCode.dead`).
- **`unusedCode`** — `dead`/`testOnly`/`total` counts derived from the `unusedCode.dead` and `unusedCode.testOnly` predicate names specifically.
- **`topFiles`** — the files with the most diagnostics, sorted by count descending.

See the module docstring in `scripts/eval_conventions.py` for the exact JSON shape (`schemaVersion`, `meta`, and the summary fields above).

## Quick start

```bash
# Baseline snapshot before the agent does anything.
uv run python scripts/eval_conventions.py run /path/to/target-repo \
  --label before --output /tmp/before.json

# ...agent does its work on the target repo...

# Snapshot after.
uv run python scripts/eval_conventions.py run /path/to/target-repo \
  --label after --output /tmp/after.json

# Compare.
uv run python scripts/eval_conventions.py compare /tmp/before.json /tmp/after.json
```

## The A/B protocol

Run the *same* coding task twice, against two fresh checkouts (or two branches) of the target repo:

- **Arm A (control)** — the agent gets the task prompt only.
- **Arm B (treatment)** — the agent additionally gets:
  1. the output of `konsistent explain` (optionally `konsistent explain --config-path path/to/konsistent.json > CLAUDE.md`, or piped straight into the agent's system prompt) injected into its context up front, so it knows the repo's structural conventions *before* writing code; and
  2. a `PostToolUse`-style hook that runs `konsistent check --files <edited-file>` after each edit and surfaces new violations back to the agent before it proceeds. See [Claude Code hook integration](./claude-code-hook.md) for a ready-made hook script and `.claude/settings.json` wiring.

Snapshot metrics once before the task (a shared baseline for both arms), then again after each arm finishes, then run three comparisons: baseline vs. Arm A, baseline vs. Arm B, and Arm A vs. Arm B directly. The last comparison isolates the effect of the guidance/hook combination.

`konsistent explain` renders the *entire* resolved configuration (every convention, plus `unusedCode` settings) as Markdown or text — there is no flag to filter it down to a single convention. If a task only plausibly touches a handful of conventions, trim the rendered output by hand before injecting it, or inject it in full; either is a reasonable choice for the treatment arm. See [`explain`](../reference/cli.md#explain) in the CLI reference for the exact output shape and flags.

## Reading the comparison output

The default `compare` output is a fixed-width text table:

1. A header naming the two labels being compared (`--label` values from each `run`, or `"before"`/`"after"` if unset).
2. Top-line summary rows (files checked, total diagnostics, errors, warnings, suppressed), each as `before -> after (delta)`.
3. A "By convention" section — one row per convention with a nonzero count on either side.
4. A "By predicate" section — same, grouped by predicate name.
5. An "Unused code" section — dead/test-only/total rows.
6. A "Regression check" line: `PASS` or `FAIL - errors increased`.

Pass `--format json` to get the same comparison as structured JSON instead — useful for feeding into a larger eval harness, a spreadsheet, or CI tooling. Its shape mirrors the table: every counted field becomes `{"before": ..., "after": ..., "delta": ...}`, and `byConvention`/`byPredicate`/`unusedCode` are keyed unions of both sides.

## Using `--fail-on-regression` in CI-style gating

`compare --fail-on-regression` makes the script exit `1` if and only if `after.errors > before.errors` — a strict increase in error-severity diagnostics. An increase in warnings alone never triggers this exit code (though it's still visible in the printed/JSON diff).

Exit code contract for `scripts/eval_conventions.py`, distinct from konsistent's own exit codes (which are only recorded informationally, in `meta.exitCode`, for each `run` snapshot):

- `0` — normal completion (no regression, or `--fail-on-regression` not passed).
- `1` — `compare --fail-on-regression` was passed and errors increased.
- `2` — harness error: bad target path, unparseable konsistent output, a missing/invalid summary file, or a subprocess timeout.

## Limitations

- **Single-repo-per-invocation.** There's no built-in fan-out across many repos; script it with a shell loop if you need to run the same A/B comparison across a fleet of target repos.
- **Structural-convention counts only**, not a full code-quality score. This measures drift against *whatever conventions the target repo's `konsistent.json` declares* — a repo with few conventions defined will show little signal regardless of actual structural drift.
- **`--max-diagnostics` is deliberately raised** to 1,000,000 by this script (vs. konsistent's own default of 100) so large diffs aren't truncated before this script counts them. `summary.errors`/`summary.warnings` in konsistent's `--format json` output are always the full pre-truncation totals regardless of `--max-diagnostics` (with a top-level `truncation: {shown, omitted}` key reporting how much was cut), so those two counts are safe either way -- but this script's own `totalDiagnostics` metric is `len(diagnostics)`, i.e. the size of the (possibly truncated) `diagnostics` array, so it still undercounts if you override `--max-diagnostics` to a low value via `--extra-arg`.
- **No daemon/history.** Each `run` is a one-shot snapshot; comparison is done by diffing two saved JSON files on disk, not by querying a running service or database.

## See also

- [CLI reference](../reference/cli.md) — `check` flags, `--format json` shape, and [`konsistent explain`](../reference/cli.md#explain).
- [Fixing violations](./fixing-violations.md) — what to do once a comparison shows regressions.
- [Suppressions](../reference/suppressions.md) — if an agent legitimately needs an exception rather than a fix.
