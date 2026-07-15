"""`help` command registration for the `konpy` CLI."""

from __future__ import annotations

import typer

from konpy._version import __version__
from konpy.cli._app_instance import app


def render_help_text() -> str:
    """Render the full `konpy help` usage text."""
    return f"""konpy v{__version__} — Enforce structural conventions in Python codebases

Usage:
  konpy [command] [options]

Commands:
  check          Check structural conventions (default)
  validate       Validate configuration
  extract-rules  Extract structural and semantic rule proposals from prose
  infer          Mine the codebase for candidate structural conventions
  explain        Render resolved conventions as agent guidance
  gate           Run a deterministic PreToolUse convention gate
  hook           Run an agentic PostToolUse verification hook
  hook-propose   Promote logged hook findings into rule proposals
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

Hook-propose options:
  [findings-path]            JSONL log (default: .konpy/hook-findings.jsonl)
  -o, --output <path>        Path for generated reusable convention pack proposal
  --rules-output <path>      Path for generated semantic-rules package
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write the rule-routing report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Timeout for the proposal agent subprocess
  --verbose                  Stream the agent CLI's own output to stderr

Exit codes (gate):
  0  allow, skipped, unreconstructable, or fail-open config/runtime warning
  1  unrecognized gate arguments only; non-blocking misconfiguration
  2  verified convention violation in proposed content

Exit codes (hook):
  0  pass, or skipped because no tool, path, or semantic rule applies
  1  fail-open configuration or infrastructure error, including invalid rules
  2  verified failure only; reasons are written to stderr

Global options:
  --help, -h                 Show help
  --version                  Print the version number"""


@app.command(name="help")
def help_command() -> None:
    """Show this help message."""
    typer.echo(render_help_text())
