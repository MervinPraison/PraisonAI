"""
Context command group for PraisonAI CLI.

Provides context management commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Context management")


@app.command("show")
def context_show(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Show current context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'show']
    if verbose:
        argv.append('--verbose')
    
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
def context_clear():
    """Clear current context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'clear']
    
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
def context_add(
    content: str = typer.Argument(..., help="Content to add to context"),
):
    """Add content to context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'add', content]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
