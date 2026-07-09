"""
Rules command group for PraisonAI CLI.

Provides rules management commands.
"""

import typer

app = typer.Typer(help="Rules management")


@app.command("list")
def rules_list():
    """List active rules."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['rules', 'list']
    
    run_wrapper_command(argv, feature="rules")


@app.command("add")
def rules_add(
    rule: str = typer.Argument(..., help="Rule to add"),
):
    """Add a rule."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['rules', 'add', rule]
    
    run_wrapper_command(argv, feature="rules")


@app.command("clear")
def rules_clear():
    """Clear all rules."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['rules', 'clear']
    
    run_wrapper_command(argv, feature="rules")
