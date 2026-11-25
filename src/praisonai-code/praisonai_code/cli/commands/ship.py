"""``praisonai ship``: commit, push and open a draft pull request. Never merges."""

import typer

app = typer.Typer(help="Commit, push and open a draft PR (never merges)")


@app.callback(invoke_without_command=True)
def ship_main(
    message: str = typer.Option(None, "--message", "-m", help="Commit message (generated if not given)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan and change nothing"),
):
    """Commit all changes, push the branch and open a draft PR. You merge it."""
    from praisonai_code.ship.flow import ShipRefused, ship_to_draft_pr

    try:
        typer.echo(ship_to_draft_pr(message=message, dry_run=dry_run))
    except ShipRefused as exc:
        typer.echo(f"ship: {exc}", err=True)
        raise typer.Exit(1)
