"""
Registry command group for PraisonAI CLI.

Provides registry management commands.
"""

import typer

app = typer.Typer(help="Registry management")


@app.command("list")
def registry_list():
    """List registry entries."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['registry', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("serve")
def registry_serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to serve on"),
):
    """Start registry server."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['registry', 'serve', '--port', str(port)]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
