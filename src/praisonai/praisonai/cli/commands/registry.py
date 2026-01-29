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
    """Start registry server.
    
    DEPRECATED: Use `praisonai serve registry` instead.
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai registry serve' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve registry' instead.\033[0m\n", file=sys.stderr)
    
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
