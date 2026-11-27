"""``praisonai approvals``: evaluate a PR against ``.praisonai/approvals.yml``."""

import dataclasses
import json
from typing import Optional

import typer

app = typer.Typer(help="Check a PR against .praisonai/approvals.yml policy")


@app.command()
def approvals_main(
    pr: Optional[str] = typer.Argument(None, help="PR number or URL (defaults to current branch's PR)"),
    policy: Optional[str] = typer.Option(None, "--policy", "-p", help="Local policy file override"),
    enforce: bool = typer.Option(False, "--enforce", help="Exit 1 on failure even when policy mode is observe"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
    comment: bool = typer.Option(False, "--comment", help="Upsert a live approval status comment on the PR"),
):
    """Evaluate a pull request against ``.praisonai/approvals.yml`` (never merges)."""
    from praisonai_code.ship import approvals
    from praisonai_code.ship.flow import ShipRefused

    try:
        report = approvals.check_pr_policy(pr, policy_path=policy)
    except (ShipRefused, ValueError) as exc:
        typer.echo(f"approvals: {exc}", err=True)
        raise typer.Exit(1)

    if comment and not approvals.post_policy_comment(pr, report):
        typer.echo("approvals: warning: failed to post status comment to PR", err=True)

    if as_json:
        typer.echo(json.dumps({**dataclasses.asdict(report), "blocking": report.blocking}, indent=2))
    else:
        typer.echo(f"approvals: {report.summary}")
        for v in report.verdicts:
            status = "PASS" if v.passed else "FAIL"
            detail = f" ({'; '.join(v.reasons)})" if v.reasons else ""
            typer.echo(f"  [{status}] {v.rule}{detail}")
    if report.blocking or (enforce and not report.passed):
        raise typer.Exit(1)
