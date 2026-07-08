"""
Endpoints command group for PraisonAI CLI.

Provides API endpoint management commands. Handlers dispatch directly to
``handle_endpoints_command`` in ``praisonai_code.cli.features.endpoints``
(bridged from the praisonai wrapper) instead of re-entering the legacy CLI.
"""

import typer

app = typer.Typer(help="API endpoint management")


def _run(argv):
    """Dispatch to the endpoints feature handler and exit with its code."""
    from praisonai_code.cli.features.endpoints import handle_endpoints_command

    raise typer.Exit(handle_endpoints_command(argv))


@app.command("list")
def endpoints_list():
    """List available endpoints."""
    _run(["list"])


@app.command("test")
def endpoints_test(
    endpoint: str = typer.Argument(..., help="Endpoint to test"),
):
    """Test an endpoint by invoking it."""
    _run(["invoke", endpoint])
