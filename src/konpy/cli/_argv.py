"""CLI argv preprocessing: default subcommand injection and `--files` expansion.

Split out of `konpy.cli.app` to keep that module under the project's
per-module line limit.
"""

from __future__ import annotations

_KNOWN_SUBCOMMANDS = {
    "check",
    "validate",
    "extract-rules",
    "infer",
    "explain",
    "gate",
    "hook",
    "review",
    "hook-propose",
    "improve",
    "init",
    "docs",
    "report",
    "verify",
    "version",
    "help",
}

_MULTI_VALUE_OPTIONS = ("--files", "--exclude")

# Options that only `report` accepts. Flags-only argv normally implies `check`,
# but `konpy --exclude vendor/**` clearly means the report, so route it there
# instead of failing with "No such option" on `check`.
_REPORT_ONLY_OPTIONS = ("--exclude", "--include-vendored")


def _expand_multi_value_options(argv: list[str]) -> list[str]:
    """Expand a single `--files a.py b.py` occurrence into repeated
    `--files a.py --files b.py` tokens, so `--files` supports both the
    already-native repeated-flag form and a single space-separated list.

    Expansion stops at the first following token that starts with `-`
    (treated as the next option) or at end of argv. Tokens after a literal
    `--` separator are never expanded. `--files=value` (single value via
    `=`) is left untouched — it is already exactly one value and is handled
    natively by Click.
    """
    expanded: list[str] = []
    index = 0
    saw_double_dash = False
    while index < len(argv):
        token = argv[index]
        if token == "--":
            saw_double_dash = True
            expanded.append(token)
            index += 1
            continue
        if saw_double_dash or token not in _MULTI_VALUE_OPTIONS:
            expanded.append(token)
            index += 1
            continue

        index += 1
        values: list[str] = []
        while index < len(argv) and not argv[index].startswith("-"):
            values.append(argv[index])
            index += 1

        if not values:
            expanded.append(token)  # bare flag; let Click raise its own error
            continue

        for value in values:
            expanded.append(token)
            expanded.append(value)

    return expanded


def _preprocess_argv(argv: list[str]) -> list[str]:
    """Expand `--files`, route bare invocations to `report`, and default to `check`.

    A truly-bare `konpy` runs the zero-config codebase report (fallow-style:
    unused code, duplication, coverage — no konpy.json required); options
    without a subcommand (e.g. `konpy --files a.py`) still imply `check`, except
    for report-only options like `--exclude`, which route to `report`.
    """
    if not argv:
        return ["report"]

    if argv == ["--version"]:
        return ["version"]

    expanded = _expand_multi_value_options(argv)

    has_subcommand = any(
        not arg.startswith("-") and arg in _KNOWN_SUBCOMMANDS for arg in expanded
    )
    has_help_flag = "--help" in expanded or "-h" in expanded

    if has_subcommand or has_help_flag:
        return expanded

    if any(
        arg == option or arg.startswith(f"{option}=")
        for arg in expanded
        for option in _REPORT_ONLY_OPTIONS
    ):
        return ["report", *expanded]

    return ["check", *expanded]
