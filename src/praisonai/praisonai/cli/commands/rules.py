"""
Rules command group for PraisonAI CLI.

Provides rules management commands.
"""

import typer

app = typer.Typer(help="Rules management")


@app.command("list")
def rules_list():
    """List active rules."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['rules', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("add")
def rules_add(
    rule: str = typer.Argument(..., help="Rule to add"),
):
    """Add a rule."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['rules', 'add', rule]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("clear")
def rules_clear():
    """Clear all rules."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['rules', 'clear']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
