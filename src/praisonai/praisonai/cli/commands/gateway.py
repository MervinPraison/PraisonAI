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
    port: Optional[int] = typer.Option(None, "--port", help="Port to listen on"),
    agents: Optional[str] = typer.Option(None, "--agents", help="Path to agent configuration file"),
    config: Optional[str] = typer.Option(None, "--config", help="Path to gateway.yaml for multi-bot mode"),
    preflight: bool = typer.Option(
        True,
        "--preflight/--no-preflight",
        help="Validate channel credentials before starting (fail fast on bad tokens)",
    ),
):
    """Start the gateway server.

    Examples:
        praisonai gateway start
        praisonai gateway start --config gateway.yaml
        praisonai gateway start --agents agents.yaml --port 9000
        praisonai gateway start --config gateway.yaml --no-preflight
        GATEWAY_PORT=9000 praisonai gateway start
    """
    import os
    from ..features.gateway import GatewayHandler

    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765

    # Pre-flight: validate channel credentials before launch so bad/expired
    # tokens fail fast with a precise per-channel reason instead of entering a
    # silent reconnect loop (#2426). Only runs in multi-bot config mode.
    if preflight and config and os.path.exists(config):
        import asyncio

        # _probe_channels() loads ~/.praisonai/.env before resolving ${VAR}
        # tokens, mirroring GatewayHandler.start() so valid env-file tokens
        # are not falsely rejected (#2426).
        channels = _load_channels(config)
        if channels:
            results = asyncio.run(_probe_channels(channels))
            all_ok = _render_probe_results(results)
            if not all_ok:
                print(
                    "\nPre-flight check failed — aborting start. "
                    "Fix the channel credentials above or pass --no-preflight to skip."
                )
                raise typer.Exit(1)

    handler = GatewayHandler()
    handler.start(host=host, port=port, agent_file=agents, config_file=config)


@app.command("stop")
def gateway_stop(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    force: bool = typer.Option(False, "--force", help="Force stop (kill process)"),
):
    """Stop a running gateway instance.

    Examples:
        praisonai gateway stop
        praisonai gateway stop --port 9000
        praisonai gateway stop --force
    """
    import os
    from ..features.gateway import GatewayHandler
    from ..output.console import get_output_controller
    
    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765
    
    handler = GatewayHandler()
    handler.stop(host=host, port=port, force=force)


@app.command("status")
def gateway_status(
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: Optional[int] = typer.Option(None, "--port", help="Gateway port"),
    daemon_only: bool = typer.Option(False, "--daemon-only", help="Show only daemon status"),
):
    """Check gateway status and daemon service status.

    Examples:
        praisonai gateway status
        praisonai gateway status --port 9000
        praisonai gateway status --daemon-only
    """
    import os
    from ..features.gateway import GatewayHandler
    from praisonai.daemon import get_daemon_status
    from ..output.console import get_output_controller
    
    # Check for GATEWAY_PORT environment variable if port not specified
    if port is None:
        try:
            port = int(os.environ.get("GATEWAY_PORT", "8765"))
        except ValueError:
            port = 8765
    
    output = get_output_controller()
    
    # Show daemon status
    try:
        daemon_status = get_daemon_status()
        platform = daemon_status.get("platform", "unknown")
        installed = daemon_status.get("installed", False)
        running = daemon_status.get("running", False)
        
        if installed:
            if running:
                output.print_success(f"Daemon service: Running ({platform})")
            else:
                output.print_warning(f"Daemon service: Installed but not running ({platform})")
        else:
            output.print_info(f"Daemon service: Not installed ({platform})")
            
        if daemon_status.get("pid"):
            output.print_info(f"Process ID: {daemon_status['pid']}")
        if daemon_status.get("error"):
            output.print_warning(f"Daemon error: {daemon_status['error']}")
            
    except Exception as e:
        output.print_error(f"Error checking daemon status: {str(e)}")
    
    # Show gateway server status if not daemon-only
    if not daemon_only:
        try:
            handler = GatewayHandler()
            handler.status(host=host, port=port)
        except Exception as e:
            output.print_error(f"Error checking gateway server status: {str(e)}")


def _resolve_env_token(value):
    """Resolve a ``${VAR}`` placeholder to its env value (pass-through otherwise)."""
    import os

    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _load_channels(config: str) -> dict:
    """Load the ``channels`` mapping from a gateway.yaml file (or exit)."""
    import os
    import yaml

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    return cfg.get("channels", {})


async def _probe_channels(channels: dict, timeout: float = 15.0) -> dict:
    """Build a lightweight Bot per channel and probe its credentials.

    Probing builds the adapter lazily and calls the platform identity API
    (Telegram getMe, Slack auth.test, …) without starting message
    processing. No agent is required. Returns ``{name: ProbeResult}``.

    Each probe is bounded by ``timeout`` (seconds) so one stuck adapter
    cannot hang the whole pre-flight; a timeout is reported as a failure.

    Loads ``~/.praisonai/.env`` first so ``${VAR}`` tokens stored there
    (e.g. by ``praisonai onboard``) resolve — mirroring what
    ``GatewayHandler.start()`` does at runtime, so every credential check
    (doctor / channels --probe / start --preflight) uses the same
    token-resolution behavior (#2426).
    """
    import asyncio as _asyncio

    # Load env-file BEFORE resolving ${VAR} tokens so all probe paths
    # (doctor, channels --probe, start --preflight) match runtime behavior.
    try:
        from ..features.gateway import _load_praisonai_env_file
        _load_praisonai_env_file()
    except Exception:  # pragma: no cover — defensive
        pass

    from praisonai.bots import Bot
    from praisonaiagents.bots import ProbeResult

    async def _probe_one(name: str, ch_cfg: dict):
        platform = ch_cfg.get("platform", name)
        token = _resolve_env_token(ch_cfg.get("token", ""))
        extras = {
            k: _resolve_env_token(v)
            for k, v in ch_cfg.items()
            if k not in ("platform", "token")
        }
        try:
            bot = Bot(platform, token=token, **extras)
            return name, await _asyncio.wait_for(bot.probe(), timeout=timeout)
        except _asyncio.TimeoutError:
            return name, ProbeResult(
                ok=False,
                platform=platform,
                error=f"probe timed out after {timeout:g}s",
            )
        except Exception as e:  # pragma: no cover — defensive
            return name, ProbeResult(ok=False, platform=platform, error=str(e))

    results = await _asyncio.gather(
        *(_probe_one(name, ch_cfg or {}) for name, ch_cfg in channels.items())
    )
    return dict(results)


def _render_probe_results(results: dict, json_output: bool = False) -> bool:
    """Print per-channel probe verdicts. Returns True if all channels passed."""
    all_ok = all(getattr(r, "ok", False) for r in results.values())

    if json_output:
        import json

        print(
            json.dumps(
                {
                    name: r.to_dict() if hasattr(r, "to_dict") else vars(r)
                    for name, r in results.items()
                },
                indent=2,
            )
        )
        return all_ok

    for name, r in results.items():
        mark = "✓" if getattr(r, "ok", False) else "✗"
        identity = getattr(r, "bot_username", None) or ""
        if getattr(r, "ok", False):
            detail = f"@{identity}" if identity else (getattr(r, "platform", "") or "")
        else:
            detail = getattr(r, "error", None) or "unknown error"
        print(f"{name:<12} {mark}  {detail}")

    return all_ok


@app.command("doctor")
def gateway_doctor(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Validate every configured channel's credentials (pre-flight check).

    Probes each channel's token and surfaces the bot identity
    (Telegram getMe, Slack auth.test, Discord identify, WhatsApp token check)
    without starting message processing. Exits non-zero if any channel fails.

    Examples:
        praisonai gateway doctor
        praisonai gateway doctor --config my-gateway.yaml --json
    """
    import asyncio

    channels = _load_channels(config)
    if not channels:
        print("No channels configured.")
        raise typer.Exit(0)

    results = asyncio.run(_probe_channels(channels))
    all_ok = _render_probe_results(results, json_output=json_output)
    if not all_ok:
        raise typer.Exit(1)


@app.command("channels")
def gateway_channels(
    config: str = typer.Option("gateway.yaml", "--config", "-c", help="Path to gateway.yaml"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    probe: bool = typer.Option(False, "--probe", help="Probe each channel's credentials"),
    available: bool = typer.Option(
        False, "--available",
        help="List all registered platforms (built-in + entry-point + custom)",
    ),
):
    """List channels configured in a gateway.yaml file.

    Examples:
        praisonai gateway channels
        praisonai gateway channels --config my-gateway.yaml --json
        praisonai gateway channels --probe
        praisonai gateway channels --available
    """
    import os
    import yaml

    if available:
        try:
            from praisonai.bots._registry import list_platforms
            platforms = sorted(list_platforms())
        except Exception as exc:
            print(f"Error: could not load platform registry: {exc}")
            raise typer.Exit(1)

        if json_output:
            import json
            print(json.dumps(platforms, indent=2))
            raise typer.Exit(0)

        try:
            from rich.table import Table
            from rich.console import Console

            console = Console()
            table = Table(title="Available Platforms")
            table.add_column("Platform", style="green")
            for platform in platforms:
                table.add_row(platform)
            console.print(table)
        except ImportError:
            print("Available platforms:")
            for platform in platforms:
                print(f"  - {platform}")
        raise typer.Exit(0)

    if not os.path.exists(config):
        print(f"Error: Config file not found: {config}")
        raise typer.Exit(1)

    with open(config) as f:
        cfg = yaml.safe_load(f) or {}

    channels = cfg.get("channels", {})

    if not channels:
        print("No channels configured.")
        raise typer.Exit(0)

    if probe:
        import asyncio

        results = asyncio.run(_probe_channels(channels))
        all_ok = _render_probe_results(results, json_output=json_output)
        if not all_ok:
            raise typer.Exit(1)
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


@app.command("pause")
def gateway_pause_channel(
    name: str = typer.Argument(help="Channel name to pause"),
    url: str = typer.Option("ws://127.0.0.1:8765", "--url", help="Gateway WebSocket URL"),
):
    """Pause a gateway channel.
    
    Examples:
        praisonai gateway pause telegram
        praisonai gateway pause discord --url ws://localhost:8000
    """
    import requests
    import sys
    from urllib.parse import urlparse, urlunparse
    
    try:
        # Parse URL and convert WebSocket to HTTP
        parsed = urlparse(url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        # Reconstruct base URL preserving path and query
        rest_url = urlunparse((
            scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment
        ))
        if not rest_url.endswith("/"):
            rest_url += "/"
        
        response = requests.post(f"{rest_url}api/channels/{name}/pause", timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("success"):
            print(f"✅ Channel '{name}' paused successfully")
        else:
            message = result.get("message", result.get("error", "Unknown error"))
            print(f"❌ Failed to pause channel '{name}': {message}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error pausing channel '{name}': {str(e)}")
        sys.exit(1)


@app.command("resume")
def gateway_resume_channel(
    name: str = typer.Argument(help="Channel name to resume"),
    url: str = typer.Option("ws://127.0.0.1:8765", "--url", help="Gateway WebSocket URL"),
):
    """Resume a paused gateway channel.
    
    Examples:
        praisonai gateway resume telegram
        praisonai gateway resume discord --url ws://localhost:8000
    """
    import requests
    import sys
    from urllib.parse import urlparse, urlunparse
    
    try:
        # Parse URL and convert WebSocket to HTTP
        parsed = urlparse(url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        # Reconstruct base URL preserving path and query
        rest_url = urlunparse((
            scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment
        ))
        if not rest_url.endswith("/"):
            rest_url += "/"
        
        response = requests.post(f"{rest_url}api/channels/{name}/resume", timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("success"):
            print(f"✅ Channel '{name}' resumed successfully")
        else:
            message = result.get("message", result.get("error", "Unknown error"))
            print(f"❌ Failed to resume channel '{name}': {message}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error resuming channel '{name}': {str(e)}")
        sys.exit(1)


@app.command("reconnect")
def gateway_reconnect_channel(
    name: str = typer.Argument(help="Channel name to reconnect"),
    url: str = typer.Option("ws://127.0.0.1:8765", "--url", help="Gateway WebSocket URL"),
):
    """Reconnect a gateway channel.
    
    Examples:
        praisonai gateway reconnect telegram
        praisonai gateway reconnect discord --url ws://localhost:8000
    """
    import requests
    import sys
    from urllib.parse import urlparse, urlunparse
    
    try:
        # Parse URL and convert WebSocket to HTTP
        parsed = urlparse(url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        # Reconstruct base URL preserving path and query
        rest_url = urlunparse((
            scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment
        ))
        if not rest_url.endswith("/"):
            rest_url += "/"
        
        response = requests.post(f"{rest_url}api/channels/{name}/reconnect", timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("success"):
            print(f"✅ Channel '{name}' reconnected successfully")
        else:
            message = result.get("message", result.get("error", "Unknown error"))
            print(f"❌ Failed to reconnect channel '{name}': {message}")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error reconnecting channel '{name}': {str(e)}")
        sys.exit(1)


@app.command("install")
def gateway_install(
    config: str = typer.Option(
        "bot.yaml", "--config",
        help="Path to bot.yaml (defaults to ./bot.yaml → ~/.praisonai/bot.yaml)",
    ),
    start: bool = typer.Option(True, "--start/--no-start", help="Start after install"),
):
    """Install the gateway as an OS daemon (LaunchAgent / systemd).
    
    Examples:
        praisonai gateway install
        praisonai gateway install --config my-bot.yaml --no-start
    """
    from praisonai.daemon import install_daemon
    from .._paths import resolve_bot_config_path
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    config = resolve_bot_config_path(config)
    
    try:
        result = install_daemon(config_path=config)
        if result.get("ok"):
            output.print_success(result.get("message", "Service installed successfully"))
            if start:
                output.print_info("Starting the service...")
                from praisonai.daemon import get_daemon_status
                status = get_daemon_status()
                if status.get("running"):
                    output.print_success("Service is now running")
                else:
                    output.print_warning("Service installed but not running. Check system logs.")
        else:
            error = result.get("error", "Installation failed")
            output.print_error(f"Installation failed: {error}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Installation error: {str(e)}")
        raise typer.Exit(1)


@app.command("uninstall")
def gateway_uninstall():
    """Uninstall the gateway daemon service.
    
    Examples:
        praisonai gateway uninstall
    """
    from praisonai.daemon import uninstall_daemon
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        result = uninstall_daemon()
        if result.get("ok"):
            output.print_success(result.get("message", "Service uninstalled successfully"))
        else:
            error = result.get("error", "Uninstallation failed")
            output.print_error(f"Uninstallation failed: {error}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Uninstallation error: {str(e)}")
        raise typer.Exit(1)


@app.command("mint-link")
def gateway_mint_link(
    ttl: int = typer.Option(600, "--ttl", help="Time-to-live in seconds (default: 600 = 10 minutes)"),
    host: str = typer.Option("127.0.0.1", "--host", help="Gateway host"),
    port: int = typer.Option(8765, "--port", help="Gateway port"),
):
    """Generate a fresh magic link for gateway authentication.
    
    Magic links provide one-click authentication without needing to
    copy/paste tokens. Links expire after the specified TTL and can
    only be used once.
    
    Examples:
        praisonai gateway mint-link
        praisonai gateway mint-link --ttl 300  # 5 minutes
        praisonai gateway mint-link --port 9000
    """
    from ..commands.mint_link import mint_fresh_link
    from ..output.console import get_output_controller
    import os
    
    output = get_output_controller()
    
    try:
        # Set environment for host/port override
        os.environ["GATEWAY_HOST"] = host
        os.environ["GATEWAY_PORT"] = str(port)
        
        magic_url = mint_fresh_link(ttl=ttl)
        
        output.print_success("Magic link generated:")
        print(f"\n{magic_url}\n")
        output.print_info(f"Expires in {ttl} seconds ({ttl//60} minutes)")
        output.print_info("Link saved to ~/.praisonai/last-link.txt")
        
    except Exception as e:
        output.print_error(f"Failed to generate magic link: {str(e)}")
        raise typer.Exit(1)


@app.command("logs")
def gateway_logs(
    lines: int = typer.Option(50, "-n", help="Number of log lines to show"),
):
    """Show daemon service logs.
    
    Examples:
        praisonai gateway logs
        praisonai gateway logs -n 100
    """
    from praisonai.daemon import _detect_platform
    from ..output.console import get_output_controller
    import subprocess
    import sys
    
    output = get_output_controller()
    plat = _detect_platform()
    
    try:
        if plat == "systemd":
            from praisonai.daemon.systemd import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found or service not installed")
        elif plat == "launchd":
            from praisonai.daemon.launchd import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found or service not installed")
        elif plat == "windows":
            from praisonai.daemon.windows import get_logs
            logs = get_logs(lines=lines)
            if logs:
                print(logs)
            else:
                output.print_warning("No logs found")
        else:
            output.print_error(f"Unsupported platform: {plat}")
            raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Error reading logs: {str(e)}")
        raise typer.Exit(1)


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
  [green]stop[/green]        Stop a running gateway instance
  [green]status[/green]      Check gateway and daemon status
  [green]doctor[/green]      Validate channel credentials (pre-flight check)
  [green]channels[/green]    List channels from gateway.yaml (use --probe to check creds)
  [green]send[/green]        Send a test message to a channel
  [green]install[/green]     Install as OS daemon service
  [green]uninstall[/green]   Uninstall daemon service
  [green]logs[/green]        Show daemon service logs
  [green]mint-link[/green]   Generate a one-time magic link (options: --ttl, --host, --port)

[bold]Multi-Bot Mode:[/bold]
  praisonai gateway start --config gateway.yaml

[bold]Standard Mode:[/bold]
  praisonai gateway start
  praisonai gateway start --agents agents.yaml --port 9000

[bold]Check Status:[/bold]
  praisonai gateway status

[bold]Channel Management:[/bold]
  praisonai gateway doctor --config gateway.yaml
  praisonai gateway channels --config gateway.yaml --probe
  praisonai gateway send --config gateway.yaml --channel telegram --channel-id 12345 -m "test"
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\\[/?[^\\]]+\\]', '', help_text)
            print(plain)
