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
  extract-rules  Extract reusable convention proposals from prose rules
  infer          Mine the codebase for candidate structural conventions
  explain        Render resolved conventions as agent guidance (markdown/text)
  hook           Run an agentic PostToolUse verification hook
  hook-propose   Promote logged hook findings into reusable convention proposals
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
  --files <path...>          Restrict checking to these files; repeatable or space-separated
  --changed                  Restrict checking to files changed since HEAD (git diff + untracked)

Validate options:
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --placeholder <name:value> Inject a placeholder value; may be repeated

Extract-rules options:
  -o, --output <path>        Path for generated reusable convention pack proposal
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write unmapped-rules report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)

Infer options:
  --include <glob>           Glob(s) of files to scan; repeatable (default: **/*.py)
  --exclude <glob>           Glob(s) to exclude from scanning; repeatable
  --test-glob <glob>         Glob(s) identifying test files; repeatable
  --min-confidence <n>       Minimum support/total ratio required to propose (default: 0.9)
  --min-support <n>          Minimum sample size required to consider a signal (default: 3)
  --max-violators <n>        Maximum violator paths listed per proposal (default: 10)
  --heuristic <name>         Restrict to specific heuristics; repeatable
  --format <format>          Report format: text, markdown, json
  -o, --output <path>        Write the proposed reusable convention pack here instead of stdout
  -r, --report <path>        Write the confidence/violators report here instead of stderr

Explain options:
  --config-path <path>       Path to konpy.json config file
  --config-package <pkg>     Unsupported in the Python port
  --format <format>          Output format: md, text
  --placeholder <name:value> Inject a placeholder value; may be repeated

Hook options:
  --match <glob>             Glob pattern to filter written/edited files; may be repeated
  --prompt <text>            Natural-language verification instruction (required)
  --agent <agent>            Verifier agent CLI to use: claude or codex (required)
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Timeout for the verifier agent subprocess (default: 300.0)
  --log <path>               Append verified fail verdicts as JSONL for hook-propose

Hook-propose options:
  [findings-path]            JSONL hook findings log (default: .konpy/hook-findings.jsonl)
  -o, --output <path>        Path for generated reusable convention pack proposal
  --agent <agent>            Agent CLI to use: auto, claude, or codex
  --report <path>            Write unmapped-rules report to this path
  --model <model>            Model passed through to the agent CLI (default: sonnet)
  --timeout <seconds>        Timeout for the proposal agent subprocess

Exit codes (hook):
  0  pass, or skipped (no match, non-write tool, sentinel active, unparseable payload)
  1  infra fail-open (missing/invalid --prompt or --agent, unrecognized options,
     agent missing, subprocess error, unparseable agent output) -- never a CLI
     usage error
  2  verdict is fail; reasons are written to stderr

Global options:
  --help, -h                 Show help
  --version                  Print the version number"""


@app.command(name="help")
def help_command() -> None:
    """Show this help message."""
    typer.echo(render_help_text())
