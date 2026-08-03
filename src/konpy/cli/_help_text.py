"""`help` command registration for the `konpy` CLI."""

from __future__ import annotations

import typer

from konpy._version import __version__
from konpy.cli._app_instance import app

_GETTING_STARTED = r"""Getting started:
  konpy               Zero-config codebase report (also: konpy report)
  konpy init          Write a strict starter konpy.json (src layout, barrel-only
                      __init__.py, typing/docstring coverage, size caps,
                      duplication ratchets, unused-code detection)
  konpy init --agents Also scaffold AGENTS.md, .claude/settings.json hooks, and a verify roster
  konpy check         Check the codebase against konpy.json
  konpy docs [topic]  Print bundled reference docs (no topic lists the topics)
  konpy explain       Render active conventions as guidance for a code-writing agent

Config: conventions live in konpy.json at the repo root; "version": "v1" is
required. Minimal example:
  {
    "version": "v1",
    "conventions": [
      {
        "name": "max-module-length",
        "description": "Modules longer than 300 lines should be split.",
        "paths": "src/**/*.py",
        "must": { "restrictFileLength": { "maxLines": 300 } }
      }
    ]
  }
Need a custom check? Try must/mustNot with matchContent (regex) before writing
a plugin — see `konpy docs predicates`, then `konpy docs plugins`."""


def render_help_text() -> str:
    """Render the full `konpy help` usage text."""
    return f"""konpy v{__version__} — Enforce structural conventions in Python codebases

Usage:
  konpy [command] [options]

  Bare `konpy` runs the zero-config codebase report (default conventions, unused code, duplication,
  coverage — no konpy.json required); options without a command imply `check`
  (e.g. `konpy --files a.py`). This help lives on `konpy help`.

{_GETTING_STARTED}

Commands:
  report         Zero-config codebase report (default for bare `konpy`)
  check          Check structural conventions (default when options are passed)
  validate       Validate configuration
  init           Write a strict starter konpy.json into the current directory
  docs           Print bundled reference docs (`konpy docs [topic]`)
  extract-rules  Extract structural and semantic rule proposals from prose
  infer          Mine the codebase for candidate structural conventions
  explain        Render resolved conventions as agent guidance
  gate           Run a deterministic PreToolUse convention gate
  review         Run an advisory PostToolUse review (findings never block)
  hook           Deprecated: prefer review or gate; agentic PostToolUse hook
  hook-propose   Promote logged hook findings into rule proposals
  improve        Ask an agent to propose a diff for one duplication finding (never applies it)
  verify         Run the config-declared verification-step roster
  version        Print the version number
  help           Show this help message

Check options:
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: default, json, github, markdown
  --verbose                  Accepted for upstream compatibility
  --max-diagnostics <n>      Maximum diagnostics to report (default: 100)
  --colors / --no-colors     Enable or disable colored default output
  --error-on-warnings        Treat warnings as errors for exit code purposes
  --diagnostic-level <level> Minimum severity to evaluate: warning or error
  --placeholder <name:value> Inject a placeholder value; may be repeated
  --show-suppressed          List diagnostics suppressed by source comments
  --files <path...>          Restrict checking to files; repeatable or space-separated
  --changed                  Restrict checking to files changed since HEAD
  --write-baseline           Record current violations as the baseline, exit 0
  --baseline <path>          Baseline file (default: konpy.baseline.json, auto-discovered)
  --show-baselined           List diagnostics hidden by the baseline

Validate options:
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --placeholder <name:value> Inject a placeholder value; may be repeated

Extract-rules options:
  -o, --output <path>        Path for generated reusable convention pack proposal
  --rules-output <path>      Path for generated semantic-rules package
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write the rule-routing report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Timeout for the extraction agent subprocess
  --verbose                  Stream the agent CLI's own output to stderr

Infer options:
  --include <glob>           Glob(s) of files to scan; repeatable (default: **/*.py)
  --exclude <glob>           Glob(s) to exclude from scanning; repeatable
  --test-glob <glob>         Glob(s) identifying test files; repeatable
  --min-confidence <n>       Minimum support/total ratio (default: 0.9)
  --min-support <n>          Minimum sample size (default: 3)
  --max-violators <n>        Maximum listed violator paths (default: 10)
  --heuristic <name>         Restrict to named heuristics; repeatable
  --format <format>          Report format: text, markdown, json
  -o, --output <path>        Write proposed pack here instead of stdout
  -r, --report <path>        Write report here instead of stderr

Explain options:
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: md, text
  --placeholder <name:value> Inject a placeholder value; may be repeated

Gate options:
  --match <glob>             Glob filtering proposed write paths; repeatable
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --diagnostic-level <level> Minimum severity to evaluate: warning or error
  --error-on-warnings        Block proposed writes on warnings
  --placeholder <name:value> Inject a placeholder value; may be repeated
  --max-diagnostics <n>      Maximum blocking diagnostics to report

Hook options:
  --match <glob>             Glob filtering written/edited files; repeatable
  --prompt <text>            One natural-language verification instruction
  --rules <path>             Semantic-rules package for batched verification
                             Exactly one of --prompt or --rules is required
  --agent <agent>            Verifier agent CLI: claude or codex (required)
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Verifier subprocess timeout (default: 300.0)
  --log <path>               Append per-rule fail findings as JSONL

Review options (same flags as hook; findings never fail the process):
  --match <glob>             Glob filtering written/edited files; repeatable
  --prompt <text>            One natural-language verification instruction
  --rules <path>             Semantic-rules package for batched verification
                             Exactly one of --prompt or --rules is required
  --agent <agent>            Verifier agent CLI: claude or codex (required)
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Verifier subprocess timeout (default: 300.0)
  --log <path>               Append per-rule fail findings as JSONL

Hook-propose options:
  [findings-path]            JSONL log (default: .konpy/hook-findings.jsonl)
  -o, --output <path>        Path for generated reusable convention pack proposal
  --rules-output <path>      Path for generated semantic-rules package
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write the rule-routing report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Timeout for the proposal agent subprocess
  --verbose                  Stream the agent CLI's own output to stderr

Improve options:
  --group <name>              Duplicate-function group to target by canonical function name
  --agent <agent>             Agent CLI to use: auto, claude, or codex
  --model <model>             Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>         Timeout for the proposing agent subprocess (default: 300.0)
  -o, --output <path>         Write the proposed diff here instead of stdout
  --config-path <path>        Only its directory anchors the scan root; need not exist

Verify options:
  --config-path <path>       Path to konpy.json config file

Exit codes (improve):
  0  the agent produced a diff-shaped response
  1  no groups, an unknown/ambiguous --group, no agent CLI found, agent
     failure, or a non-diff-shaped response (still printed to stdout)

Exit codes (gate):
  0  allow, skipped, unreconstructable, or fail-open config/runtime warning
  1  unrecognized gate arguments only; non-blocking misconfiguration
  2  verified convention violation in proposed content

Exit codes (hook):
  0  pass, or skipped because no tool, path, or semantic rule applies
  1  fail-open configuration or infrastructure error, including invalid rules
  2  verified failure only; reasons are written to stderr

Exit codes (review):
  0  always, except local misconfiguration; findings never fail the process
  1  local misconfiguration only: bad flags or an unreadable/invalid rules file

Global options:
  --help, -h                 Show help
  --version                  Print the version number"""


@app.command(name="help")
def help_command() -> None:
    """Show this help message."""
    typer.echo(render_help_text())
