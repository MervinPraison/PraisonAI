"""
UI command group for PraisonAI CLI.

Provides web UI commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Web UI management")


@app.callback(invoke_without_command=True)
def ui_main(
    ctx: typer.Context,
    port: int = typer.Option(8080, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the web UI.
    
    Examples:
        praisonai ui
        praisonai ui --port 3000
        praisonai ui --public
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['ui']
    argv.extend(['--port', str(port)])
    argv.extend(['--host', host])
    if public:
        argv.append('--public')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
