"""
Registry command group for PraisonAI CLI.

Provides registry management commands. Handlers dispatch directly to
``handle_registry_command`` in ``praisonai_code.cli.features.registry``
(bridged from the praisonai wrapper) instead of re-entering the legacy CLI.
"""

import sys

import typer

app = typer.Typer(help="Registry management")


def _run(argv):
    """Dispatch to the registry feature handler and exit with its code."""
    from praisonai_code.cli.features.registry import handle_registry_command

    raise typer.Exit(handle_registry_command(argv))


@app.command("list")
def registry_list():
    """List registry entries."""
    _run(["list"])


@app.command("serve")
def registry_serve(
    port: int = typer.Option(7777, "--port", "-p", help="Port to serve on"),
):
    """Start registry server.

    DEPRECATED: Use `praisonai serve registry` instead.
    """
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai registry serve' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve registry' instead.\033[0m\n", file=sys.stderr)

    _run(["serve", "--port", str(port)])
