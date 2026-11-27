"""``praisonai steward``: watch a PR and fix checks, conflicts, and review threads."""

from typing import Optional

import typer

app = typer.Typer(help="Watch a PR and fix checks, conflicts, and review threads (never merges)")


@app.command()
def steward_main(
    pr: Optional[str] = typer.Argument(None, help="PR number or URL (defaults to current branch's PR)"),
    interval: float = typer.Option(60.0, "--interval", help="Poll interval in seconds"),
    max_days: float = typer.Option(7.0, "--max-days", help="Stop after this many days"),
    max_attempts: int = typer.Option(3, "--max-attempts", help="Max attempts per failing check or thread"),
    once: bool = typer.Option(False, "--once", help="Run a single check/fix cycle and exit (for CI)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (e.g. gpt-4o-mini, ollama/llama3.2)"),
):
    """Watch a pull request and fix failing checks, conflicts, and review threads. Never merges."""
    from praisonai_code.ship.flow import ShipRefused
    from praisonai_code.ship.steward_loop import watch_pr

    try:
        watch_pr(pr, interval=interval, max_days=max_days, max_attempts=max_attempts,
                 once=once, llm=model, on_event=typer.echo)
    except ShipRefused as exc:
        typer.echo(f"steward: {exc}", err=True)
        raise typer.Exit(1)
