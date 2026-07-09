"""
Hooks command group for PraisonAI CLI.

Provides hook management commands.
"""

import typer

app = typer.Typer(help="Hook management")


@app.command("list")
def hooks_list():
    """List available hooks."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['hooks', 'list']
    
    run_wrapper_command(argv, feature="hooks")


@app.command("add")
def hooks_add(
    name: str = typer.Argument(..., help="Hook name"),
    event: str = typer.Option(..., "--event", "-e", help="Event to hook into"),
):
    """Add a hook."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['hooks', 'add', name, '--event', event]
    
    run_wrapper_command(argv, feature="hooks")


@app.command("remove")
def hooks_remove(
    name: str = typer.Argument(..., help="Hook name to remove"),
):
    """Remove a hook."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['hooks', 'remove', name]
    
    run_wrapper_command(argv, feature="hooks")
