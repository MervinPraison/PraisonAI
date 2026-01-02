"""
Endpoints command group for PraisonAI CLI.

Provides API endpoint management commands.
"""

import typer

app = typer.Typer(help="API endpoint management")


@app.command("list")
def endpoints_list():
    """List available endpoints."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['endpoints', 'list']
    
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
def endpoints_test(
    endpoint: str = typer.Argument(..., help="Endpoint to test"),
):
    """Test an endpoint."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['endpoints', 'test', endpoint]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
