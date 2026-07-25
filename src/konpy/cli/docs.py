"""`konpy docs` implementation: print bundled reference docs to stdout.

The docs ship inside the wheel, so a pip/uv install has an offline route from
`--help` to the full config-language reference without a repo checkout.
"""

from __future__ import annotations

import typer

from konpy.cli._packaged_docs import available_reference_topics, read_reference_doc
from konpy.config.errors import Err, Ok


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def render_topic_listing() -> str:
    """Render the available topics, one per line with the doc's title."""
    lines = ["Bundled reference docs (print one with `konpy docs <topic>`):"]
    for topic in available_reference_topics():
        doc = read_reference_doc(topic)
        heading = _first_heading(doc.value) if isinstance(doc, Ok) else ""
        lines.append(f"  {topic:<24} {heading}".rstrip())
    return "\n".join(lines)


def run_docs_command(*, topic: str | None) -> int:
    """Print the named reference doc, or list available topics."""
    if topic is None:
        typer.echo(render_topic_listing())
        return 0

    doc = read_reference_doc(topic)
    if isinstance(doc, Err):
        if topic in available_reference_topics():
            typer.echo(doc.error, err=True)
        else:
            typer.echo(f"Unknown docs topic: {topic}", err=True)
            typer.echo(render_topic_listing(), err=True)
        return 1

    typer.echo(doc.value)
    return 0


__all__ = [
    "render_topic_listing",
    "run_docs_command",
]
