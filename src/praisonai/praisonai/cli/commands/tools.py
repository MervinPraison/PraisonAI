"""
Tools command group for PraisonAI CLI.

Provides tool management commands.
"""

import typer

app = typer.Typer(help="Tool management")


@app.command("list")
def tools_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available tools."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['tools', 'list']
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


@app.command("info")
def tools_info(
    name: str = typer.Argument(..., help="Tool name"),
):
    """Show tool information."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['tools', 'info', name]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("test")
def tools_test(
    name: str = typer.Argument(..., help="Tool name to test"),
):
    """Test a tool."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['tools', 'test', name]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
