"""``praisonai ship``: commit, push, open a draft PR, self-review, and optionally watch."""

from typing import Optional
import typer

app = typer.Typer(help="Commit, push and open a draft PR (never merges)")


@app.command()
def ship_main(
    target: Optional[str] = typer.Argument(None, help="PR number/URL, effort (low..max), +reviewer, or review|init|check|ui"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Commit message (generated if not given)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan and change nothing"),
    effort: str = typer.Option("high", "--effort", help="Self-review effort: low|medium|high|xhigh|max (or quick|standard|deep)"),
    model: Optional[str] = typer.Option(None, "--model", help="Model name (e.g. gpt-4o-mini, ollama/llama3.2)"),
    github: bool = typer.Option(False, "--github", help="With `ship init`, sync detected LLM key & model to GitHub Actions"),
    review: bool = typer.Option(True, "--review/--no-review", help="Run self-review after opening the PR"),
    post_review: bool = typer.Option(False, "--post-review", help="Post self-review findings as a PR comment"),
    watch: bool = typer.Option(False, "--watch", help="Watch the PR with steward after shipping"),
    reviewer: Optional[str] = typer.Option(None, "--reviewer", help="Request a GitHub reviewer"),
):
    """Commit all changes, push the branch, open a draft PR, and self-review. You merge it."""
    from praisonai_code.ship.flow import ShipRefused

    if target in ("init", "check", "ui", "review"):
        if target == "check":
            from praisonai_code.ship.onboard import check_readiness, format_readiness

            typer.echo(format_readiness(check_readiness()))
            return
        if target == "init":
            from praisonai_code.ship.onboard import format_init_result, init_repo

            try:
                res = init_repo(dry_run=dry_run, github=github, model=model, effort=effort)
            except (ShipRefused, ValueError) as exc:
                typer.echo(f"ship: {exc}", err=True)
                raise typer.Exit(1)
            typer.echo(format_init_result(res, dry_run=dry_run))
            return
        if target == "review":
            from praisonai_code.ship import is_ship_disabled
            from praisonai_code.ship import ui_service

            if reason := is_ship_disabled():
                typer.echo(f"ship: {reason}", err=True)
                raise typer.Exit(1)
            repo = ui_service.get_repo_root()
            try:
                if dry_run:
                    diff_text, files, source = ui_service.get_diff_bundle(repo)
                    if not diff_text.strip():
                        typer.echo("ship review: no local changes to review")
                    else:
                        names = ", ".join(f.path for f in files) or "(diff)"
                        typer.echo(f"Would review {len(files)} file(s) from {source} (effort={effort}): {names}")
                    return
                res = ui_service.run_review(repo, effort=effort, model=model)
            except (ShipRefused, ValueError) as exc:
                typer.echo(f"ship: {exc}", err=True)
                raise typer.Exit(1)
            if not res.get("diff"):
                typer.echo("ship review: no local changes to review")
                return
            findings = res.get("findings") or []
            if not findings:
                typer.echo(f"ship review: no issues found (source: {res['source']}, effort: {effort})")
                return
            typer.echo(
                f"ship review: found {len(findings)} issue(s) (severity: {res['severity']}, source: {res['source']})"
            )
            for f in findings:
                loc = f"{f['path']}:{f['line']}" if f.get("line") else f["path"]
                fix = f" — {f['fix']}" if f.get("fix") else ""
                typer.echo(f"  [{f['severity']}] {loc}: {f['title']}{fix}")
            return
        import importlib.util
        import os

        if importlib.util.find_spec("praisonaiui") is None:
            typer.echo('ship: Visual Web UI requires PraisonAIUI. Install with: pip install "praisonai-code[ui]"', err=True)
            raise typer.Exit(1)
        from praisonai_code.ship.ui_plugin import serve_openship

        port = int(os.environ.get("OPENSHIP_PORT", "8765"))
        serve_openship(host="127.0.0.1", port=port, server_name="praisonai-code ship ui")
        return

    from praisonai_code.ship import orchestrate
    try:
        res = orchestrate.ship(target, message=message, dry_run=dry_run, effort=effort, model=model,
                               review=review, post_review=post_review, watch=watch, reviewer=reviewer, on_event=typer.echo)
    except (ShipRefused, ValueError) as exc:
        typer.echo(f"ship: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(res.dry_run_plan or res.pr_url)
    if not res.dry_run_plan and res.findings:
        typer.echo(f"ship: self-review found {len(res.findings)} issue(s) (severity: {res.severity})")
        for f in res.findings:
            typer.echo(f"  [{f.severity}] {f.path}{f':{f.line}' if f.line else ''}: {f.title}" + (f" — {f.fix}" if f.fix else ""))
