"""``praisonai ship``: commit, push, open a draft PR, self-review, and optionally watch."""

from typing import Optional

import typer

app = typer.Typer(help="Commit, push and open a draft PR (never merges)")


@app.command()
def ship_main(
    target: Optional[str] = typer.Argument(None, help="PR number/URL, or +reviewer"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Commit message (generated if not given)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan and change nothing"),
    effort: str = typer.Option("high", "--effort", help="Self-review effort: low|medium|high|xhigh|max"),
    model: Optional[str] = typer.Option(None, "--model", help="Model name (e.g. gpt-4o-mini, ollama/llama3.2)"),
    review: bool = typer.Option(True, "--review/--no-review", help="Run self-review after opening the PR"),
    post_review: bool = typer.Option(False, "--post-review", help="Post self-review findings as a PR comment"),
    watch: bool = typer.Option(False, "--watch", help="Watch the PR with steward after shipping"),
    reviewer: Optional[str] = typer.Option(None, "--reviewer", help="Request a GitHub reviewer"),
):
    """Commit all changes, push the branch, open a draft PR, and self-review. You merge it."""
    from praisonai_code.ship import orchestrate
    from praisonai_code.ship.flow import ShipRefused

    try:
        res = orchestrate.ship(target, message=message, dry_run=dry_run, effort=effort, model=model,
                               review=review, post_review=post_review, watch=watch, reviewer=reviewer)
    except (ShipRefused, ValueError) as exc:
        typer.echo(f"ship: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(res.dry_run_plan or res.pr_url)
    if not res.dry_run_plan and res.findings:
        typer.echo(f"ship: self-review found {len(res.findings)} issue(s) (severity: {res.severity})")
