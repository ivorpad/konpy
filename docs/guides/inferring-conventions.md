# Inferring conventions from an existing codebase

`konpy infer` mines a repository for candidate structural conventions — statistical regularities strong enough to be worth enforcing — and emits a reviewable, `ReusableConventionsPackageV1`-shaped proposed pack plus a confidence/violators report. This is the same output contract `konpy extract-rules` uses: `{"conventionSpecVersion": "v1", "conventions": [...]}`, validated against the reusable-pack schema before it is printed or written — never a `konpy.json`/`RawConfigV1`-shaped document, so a proposal can never be mistaken for (or accidentally consumed as) a real config. It never edits `konpy.json`, never reads one, and requires no agent call: all six heuristics are deterministic, running over the same `ast`/filesystem walkers `check` uses.

Think of it as the reverse of `check`: instead of telling you where your codebase violates known rules, it tells you which rules your codebase already mostly follows.

## Basic workflow

```bash
konpy infer
```

By default, the proposed pack prints to stdout and the report prints to stderr, so you can pipe the pack straight to a file while still seeing the report in your terminal:

```bash
konpy infer > konpy.infer.pack.json
```

Or write both to explicit files:

```bash
konpy infer -o konpy.infer.pack.json -r infer-report.md --format markdown
```

A proposal looks like this (one entry per convention in the `conventions` array):

```json
{
  "name": "infer-export-suffix-src-services-service",
  "description": "Inferred: 47/50 files in \"src/services\" matching *_service.py export a `{name}Service` class (94% confidence).",
  "severity": "warning",
  "paths": "src/services/{name}_service.py",
  "must": {
    "exportClasses": ["${name.toPascalCase()}Service"]
  }
}
```

Every proposal is `severity: "warning"`, so pointing `check` at a freshly inferred config never hard-fails CI before you have reviewed it.

## The six heuristics

| Heuristic | Grouping | What it measures | Predicate produced |
| --- | --- | --- | --- |
| `export-suffix` | exact directory + suffix token (`Service`, `Adapter`, `Repository`, …) | `{name}_<suffix>.py` files export a matching `{Name}<Suffix>` class | `must.exportClasses` |
| `paired-test-file` | exact directory | production modules have a matching `test_<name>.py`/`<name>_test.py` file | `must.havePairedFile` |
| `docstring-coverage` | top-level path segment | modules/classes/public functions have docstrings | `must.haveDocstrings` |
| `annotate-functions-coverage` | top-level path segment | public functions annotate params/return types | `must.annotateFunctions` |
| `barrel-usage` | top-level path segment | `__init__.py` files contain only barrel statements | `must.areBarrelFiles` |
| `import-dominance` | top-level path segment | non-barrel modules prefer absolute over relative imports | `mustNot.importFromCurrentDir`/`importFromParents` |

`import-dominance` only ever proposes the "prefers absolute imports" direction — it has no code path that proposes "prefers relative imports," regardless of thresholds. A low absolute-import rate simply lands the signal in the report's skipped section, never as a "you should use relative imports" proposal.

`docstring-coverage` and `annotate-functions-coverage` each measure two-or-three independent sub-signals (module/class/function docstrings; params/returns annotations) and merge whichever ones clear the threshold into a single convention, explicitly setting every option key (`true` for included kinds, `false` for excluded ones) so a later config change can't silently re-enable a kind that wasn't actually measured as passing.

Restrict to specific heuristics with `--heuristic` (repeatable):

```bash
konpy infer --heuristic export-suffix --heuristic paired-test-file
```

## Tuning `--min-confidence` and `--min-support`

Every signal is a `(support, total)` pair — how many files matched the pattern out of how many were eligible. Two thresholds decide whether it becomes a proposal:

- **`--min-support`** (default `3`): the sample size (`total`) must be at least this large. Below it, a signal is too thin to trust and is reported in the "skipped" section with `reason: "below-min-support"`.
- **`--min-confidence`** (default `0.9`): the pass rate (`support / total`) must be at least this. Below it, the signal is reported with `reason: "below-min-confidence"`.

Both comparisons are inclusive (`>=`). Raise `--min-confidence` for a stricter, higher-signal proposal set; lower it (together with `--min-support`) to see near-misses and marginal patterns you might still want to adopt deliberately:

```bash
konpy infer --min-confidence 0.75 --min-support 2
```

`--max-violators` caps how many violator paths are listed per proposal in the report (default `10`); the underlying counts (`support`/`total`) are always exact, and an `omittedViolators`/`...and N more` note tells you how many were cut.

## Reading the report

The report (`--format text|markdown|json`, default `text`) lists every proposal with its heuristic, scope, `support/total`, confidence percentage, convention name, and violator files — and every skipped signal with its reason, so you can see what almost qualified:

```text
Proposals (3):
[export-suffix] src/services (47/50, 94% confidence)
  convention: infer-export-suffix-src-services-service
  violators:
    - src/services/legacy_thing.py

Skipped signals (1):
[import-dominance] scripts: 1/2 (50% confidence) — below-min-confidence
```

Use `--format json` when scripting around the output; the top-level keys are `filesScanned`, `testFilesExcluded`, `filesSkippedUnparsable`, `filesSkippedUnreadable`, `proposals`, and `skipped`.

## Review before use

`infer` output is a discovery aid, not a linter. After generation:

1. Read the report next to the proposed pack — every proposal's violator list tells you exactly which files would need fixing (or excluding) if you adopted it.
2. Delete or narrow proposals that don't reflect an intentional convention — six-heuristic pattern mining will surface real regularities *and* coincidences.
3. Merge the survivors into your real `konpy.json` by hand (copy the convention objects in, or point `conventionSources`/`extends` at the saved pack file), then run `konpy check` to see the true violation count before committing to enforcing it as an error.

## Known limitations

- **Fixed-depth scoping.** `export-suffix` and `paired-test-file` group by *exact* directory, not a recursive `**` pattern, because the `{name}` placeholder capture requires the convention's `paths` pattern and the matched file path to have the same segment count. A repo with many leaf directories (e.g. several `*/services/` subpackages) will get one small proposal per directory instead of one repo-wide rule. This is a grammar constraint, not a bug — merge near-duplicate proposals by hand if you want one recursive rule.
- **Fixed suffix vocabulary.** `export-suffix` only recognizes a hard-coded list of suffixes (`Service`, `Adapter`, `Repository`, `Handler`, `Manager`, `Controller`, `Factory`, `Builder`, `Client`, `Provider`, `Gateway`, `Validator`, `Serializer`, `Middleware`, `Strategy`, `Worker`, `Resolver`). Other vocabularies (`*_impl.py`, `*_dao.py`, …) produce no export-suffix proposals in this release.
- **No existing-config awareness.** `infer` always mines from a blank slate; it does not check whether a pattern is already enforced in your `konpy.json` and will happily re-propose something you already have.
- **Non-stable names.** Convention names are regenerated fresh on every run (including deterministic `-2`/`-3` suffixing on directory-slug collisions), not diffed against a previous run — a directory rename can shift names across runs.

See [`docs/reference/cli.md#infer`](../reference/cli.md#infer) for the full flag reference and exit codes.
