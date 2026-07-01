"""
Agents command group for PraisonAI CLI.

Provides agent management commands.
"""

import typer

app = typer.Typer(help="Agent management")


@app.command("list")
def agents_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available agents."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['agents', 'list']
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


@app.command("create")
def agents_create(
    name: str = typer.Argument(..., help="Agent name"),
    template: str = typer.Option(None, "--template", "-t", help="Template to use"),
):
    """Create a new agent."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['agents', 'create', name]
    if template:
        argv.extend(['--template', template])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("info")
def agents_info(
    name: str = typer.Argument(..., help="Agent name"),
):
    """Show agent information."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['agents', 'info', name]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
