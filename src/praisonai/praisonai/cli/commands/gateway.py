"""
Gateway command group for PraisonAI CLI.

Provides commands for managing the WebSocket gateway with multi-bot support.
"""

from typing import Optional

import typer

app = typer.Typer(
    help="Manage the PraisonAI Gateway server",
    no_args_is_help=True,
)


@app.command("start")
def gateway_start(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", help="Port to listen on"),
    agents: Optional[str] = typer.Option(None, "--agents", help="Path to agent configuration file"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to gateway.yaml for multi-bot mode"),
):
    """Start the gateway server.

    Examples:
        praisonai gateway start
        praisonai gateway start --config gateway.yaml
        praisonai gateway start --agents agents.yaml --port 9000
    """
    from ..features.gateway import GatewayHandler

    handler = GatewayHandler()
    handler.start(host=host, port=port, agent_file=agents, config_file=config)


@app.command("status")
def gateway_status(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: int = typer.Option(8765, "--port", help="Gateway port"),
):
    """Check gateway status.

    Examples:
        praisonai gateway status
        praisonai gateway status --port 9000
    """
    from ..features.gateway import GatewayHandler

    handler = GatewayHandler()
    handler.status(host=host, port=port)


@app.callback(invoke_without_command=True)
def gateway_callback(ctx: typer.Context):
    """Show gateway help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Gateway - Multi-Bot WebSocket Server[/bold cyan]

Manage the gateway server: praisonai gateway <command>

[bold]Commands:[/bold]
  [green]start[/green]     Start the gateway server
  [green]status[/green]    Check gateway status

[bold]Multi-Bot Mode:[/bold]
  praisonai gateway start --config gateway.yaml

[bold]Standard Mode:[/bold]
  praisonai gateway start
  praisonai gateway start --agents agents.yaml --port 9000

[bold]Check Status:[/bold]
  praisonai gateway status
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
