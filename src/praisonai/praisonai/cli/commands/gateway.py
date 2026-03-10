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


@app.command("channels")
def gateway_channels(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List channels configured in a gateway.yaml file.

    Examples:
        praisonai gateway channels
        praisonai gateway channels --config my-gateway.yaml --json
    """
    import os
    import yaml

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    channels = cfg.get("channels", {})

    if not channels:
        print("No channels configured.")
        raise typer.Exit(0)

    if json_output:
        import json
        print(json.dumps(channels, indent=2))
        raise typer.Exit(0)

    try:
        from rich.table import Table
        from rich.console import Console

        console = Console()
        table = Table(title="Configured Channels")
        table.add_column("Name", style="cyan")
        table.add_column("Platform", style="green")
        table.add_column("Token", style="yellow")
        table.add_column("Config Keys", style="dim")

        for name, ch_cfg in channels.items():
            platform = ch_cfg.get("platform", "unknown")
            token_val = ch_cfg.get("token", "")
            has_token = "✅ set" if token_val else "❌ missing"
            keys = ", ".join(
                k for k in ch_cfg.keys() if k not in ("platform", "token")
            )
            table.add_row(name, platform, has_token, keys or "—")

        console.print(table)
    except ImportError:
        print(f"{'Name':<20} {'Platform':<12} {'Token':<12}")
        print("-" * 44)
        for name, ch_cfg in channels.items():
            platform = ch_cfg.get("platform", "unknown")
            has_token = "set" if ch_cfg.get("token") else "missing"
            print(f"{name:<20} {platform:<12} {has_token:<12}")


@app.command("send")
def gateway_send(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    channel: str = typer.Option(..., "--channel", help="Channel name from config (e.g. 'telegram')"),
    channel_id: str = typer.Option(..., "--channel-id", help="Target chat/channel ID"),
    message: str = typer.Option(..., "--message", "-m", help="Message text to send"),
    thread_id: Optional[str] = typer.Option(None, "--thread-id", help="Optional thread ID"),
):
    """Send a one-shot test message to a channel bot.

    Instantiates the bot from gateway.yaml config, sends the message, then exits.
    Useful for testing scheduled delivery targets.

    Examples:
        praisonai gateway send --config gateway.yaml --channel telegram --channel-id 12345 -m "Hello"
    """
    import os
    import asyncio
    import yaml

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    channels_cfg = cfg.get("channels", {})
    ch_cfg = channels_cfg.get(channel)

    if not ch_cfg:
        available = ", ".join(channels_cfg.keys()) if channels_cfg else "(none)"
        print(f"Error: Channel '{channel}' not found in config. Available: {available}")
        raise typer.Exit(1)

    platform = ch_cfg.get("platform", channel)
    token = ch_cfg.get("token", "")

    # Resolve env vars in token
    if token and token.startswith("${") and token.endswith("}"):
        env_var = token[2:-1]
        token = os.environ.get(env_var, "")
        if not token:
            print(f"Error: Environment variable {env_var} not set")
            raise typer.Exit(1)

    async def _send():
        try:
            from praisonai.gateway.server import WebSocketGateway
            bot = WebSocketGateway._create_bot(channel, ch_cfg)
        except Exception as e:
            print(f"Error creating bot: {e}")
            raise typer.Exit(1)

        try:
            await bot.start()
            await asyncio.sleep(1)  # Let bot initialise
            result = await bot.send_message(
                channel_id, message, thread_id=thread_id,
            )
            print(f"✅ Message sent to {channel}:{channel_id}")
            if hasattr(result, "message_id"):
                print(f"   Message ID: {result.message_id}")
        except Exception as e:
            print(f"❌ Send failed: {e}")
            raise typer.Exit(1)
        finally:
            try:
                await bot.stop()
            except Exception:
                pass

    try:
        asyncio.run(_send())
    except typer.Exit:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def gateway_callback(ctx: typer.Context):
    """Show gateway help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Gateway - Multi-Bot WebSocket Server[/bold cyan]

Manage the gateway server: praisonai gateway <command>

[bold]Commands:[/bold]
  [green]start[/green]       Start the gateway server
  [green]status[/green]      Check gateway status
  [green]channels[/green]    List channels from gateway.yaml
  [green]send[/green]        Send a test message to a channel

[bold]Multi-Bot Mode:[/bold]
  praisonai gateway start --config gateway.yaml

[bold]Standard Mode:[/bold]
  praisonai gateway start
  praisonai gateway start --agents agents.yaml --port 9000

[bold]Check Status:[/bold]
  praisonai gateway status

[bold]Channel Management:[/bold]
  praisonai gateway channels --config gateway.yaml
  praisonai gateway send --config gateway.yaml --channel telegram --channel-id 12345 -m "test"
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\\[/?[^\\]]+\\]', '', help_text)
            print(plain)
