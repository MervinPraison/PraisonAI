"""
Hooks command group for PraisonAI CLI.

Provides hook management commands.

Only actions the legacy handler actually implements are registered here.
``add`` and ``remove`` used to be advertised but were never implemented: the
handler printed "Unknown hooks action" and the dispatcher still exited 0, so a
script that "added" a hook succeeded while doing nothing. Hooks are configured
by editing the file that ``praisonai hooks init`` creates.
"""

import typer

app = typer.Typer(help="Hook management")


@app.command("list")
def hooks_list():
    """List configured hooks."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    run_wrapper_command(['hooks', 'list'], feature="hooks")


@app.command("stats")
def hooks_stats():
    """Show hooks statistics."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    run_wrapper_command(['hooks', 'stats'], feature="hooks")


@app.command("init")
def hooks_init():
    """Create the hooks.json template in this workspace."""
    from praisonai_code._wrapper_bridge import run_wrapper_command

    run_wrapper_command(['hooks', 'init'], feature="hooks")
