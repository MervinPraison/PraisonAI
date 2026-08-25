"""``praisonai-train models`` — what this can actually load.

`model_name` was free text with no validation, so a typo was caught by Hugging
Face after a download, and nothing told a new user which models work.

In its own module rather than alongside the post-training commands, so the
catalog does not depend on them.
"""
from __future__ import annotations

import json
from typing import Optional

import typer

from praisonai_train.cli.commands.train import app


@app.command("models")
def models(
    search: Optional[str] = typer.Argument(None, help="Filter, e.g. 'gemma' or '7b'."),
    as_json: bool = typer.Option(False, "--json", "-j"),
    limit: int = typer.Option(40, "--limit", "-n", help="0 for all."),
):
    """Models unsloth knows how to load."""
    from praisonai_train.cli.output.console import get_output_controller
    from praisonai_train.models import CURATED, known_models

    catalog = known_models()
    if search:
        needle = search.lower()
        catalog = tuple(m for m in catalog if needle in m.lower())
    if as_json:
        typer.echo(json.dumps(list(catalog), indent=2))
        return
    if not catalog:
        get_output_controller().print_error(
            f"Nothing matches '{search}'",
            remediation="Try a family name (gemma, qwen, llama) or a size (7b).")
        raise typer.Exit(1)
    shown = catalog if limit == 0 else catalog[:limit]
    for name in shown:
        mark = "*" if name in CURATED else " "
        typer.echo(f" {mark} {name}")
    if len(shown) < len(catalog):
        typer.echo(f"\n{len(shown)} of {len(catalog)}; -n 0 for all.")
    else:
        typer.echo(f"\n{len(catalog)} model(s). * = a good starting point.")
