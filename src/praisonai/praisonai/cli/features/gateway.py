"""
Gateway CLI commands for PraisonAI.

Provides CLI commands for managing the WebSocket gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _load_praisonai_env_file() -> Dict[str, str]:
    """Load ``~/.praisonai/.env`` into ``os.environ`` (without overwriting).

    Daemons launched by ``launchd`` / ``systemd`` don't inherit the user's
    shell env and don't auto-source dotfiles, so secrets written by
    ``praisonai onboard`` (e.g. ``TELEGRAM_BOT_TOKEN``) are missing when
    the gateway starts in the background. We load them here so the
    YAML ``${VAR}`` substitution in ``GatewayServer.load_gateway_config``
    resolves correctly.

    Existing ``os.environ`` values take precedence (so user-set shell
    vars always win). Returns the dict of keys we loaded (for logging).
    """
    env_path = Path(os.environ.get("PRAISONAI_ENV_FILE")
                    or (Path.home() / ".praisonai" / ".env"))
    loaded: Dict[str, str] = {}
    if not env_path.exists():
        return loaded
    try:
        for raw in env_path.read_text().splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            if k in os.environ:
                continue  # don't clobber existing env
            os.environ[k] = v
            loaded[k] = v
    except OSError as exc:
        logger.warning("Could not read %s: %s", env_path, exc)
    if loaded:
        logger.info(
            "Loaded %d env var(s) from %s: %s",
            len(loaded), env_path, ", ".join(sorted(loaded.keys())),
        )
    return loaded


class GatewayHandler:
    """Handler for gateway CLI commands."""
    
    def __init__(self):
        self._gateway = None
    
    def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        agent_file: Optional[str] = None,
        config_file: Optional[str] = None,
    ) -> None:
        """Start the gateway server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            agent_file: Optional path to agent configuration file
            config_file: Optional path to gateway.yaml for multi-bot mode
        """
        # Ensure INFO-level logs surface to bot-stdout.log / bot-stderr.log
        # when running under launchd / systemd. Many key lifecycle events
        # (bot start, channel routing, scheduler tick, retries) are already
        # emitted via `logger.info()` — they just weren't visible with the
        # default WARNING root level. Only configure if nothing is set yet,
        # so users/embedders keep control.
        _root = logging.getLogger()
        if not _root.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(name)s %(levelname)s %(message)s",
            )
        if _root.level > logging.INFO or _root.level == logging.NOTSET:
            _root.setLevel(logging.INFO)

        # Load ~/.praisonai/.env BEFORE any config parsing or ${VAR}
        # substitution — daemons don't inherit shell env.
        _load_praisonai_env_file()
        logger.info(
            "Gateway starting (host=%s port=%s config=%s agents=%s)",
            host, port, config_file or "-", agent_file or "-",
        )
        try:
            from praisonai.gateway import WebSocketGateway
            from praisonaiagents.gateway import GatewayConfig
        except ImportError as e:
            print(f"Error: Gateway requires additional dependencies. {e}")
            print("Install with: pip install praisonai[api]")
            return
        
        # Multi-bot mode: load from gateway.yaml
        if config_file:
            config = GatewayConfig(host=host, port=port)
            self._gateway = WebSocketGateway(config=config)
            print(f"Loading gateway config from {config_file}")
            try:
                asyncio.run(self._gateway.start_with_config(config_file))
            except KeyboardInterrupt:
                print("\nStopping gateway...")
                asyncio.run(self._gateway.stop_channels())
                asyncio.run(self._gateway.stop())
            except FileNotFoundError as e:
                print(f"Error: {e}")
            except Exception as e:
                print(f"Error starting gateway: {e}")
            return
        
        # Standard WebSocket-only mode
        config = GatewayConfig(host=host, port=port)
        self._gateway = WebSocketGateway(config=config)
        
        if agent_file:
            self._load_agents_from_file(agent_file)
        
        print(f"Starting gateway on ws://{host}:{port}")
        print("Press Ctrl+C to stop")
        
        try:
            asyncio.run(self._gateway.start())
        except KeyboardInterrupt:
            print("\nStopping gateway...")
            asyncio.run(self._gateway.stop())
    
    def _load_agents_from_file(self, file_path: str) -> None:
        """Load agents from a configuration file."""
        import os
        import yaml
        
        if not os.path.exists(file_path):
            print(f"Warning: Agent file not found: {file_path}")
            return
        
        try:
            with open(file_path, "r") as f:
                config = yaml.safe_load(f)
            
            if "agents" in config:
                from praisonaiagents import Agent
                
                for agent_config in config["agents"]:
                    agent = Agent(
                        name=agent_config.get("name", "agent"),
                        instructions=agent_config.get("instructions", ""),
                        llm=agent_config.get("llm"),
                    )
                    agent_id = self._gateway.register_agent(agent)
                    print(f"Registered agent: {agent_id}")
        except Exception as e:
            print(f"Error loading agents: {e}")
    
    def status(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Check gateway status.
        
        Args:
            host: Gateway host
            port: Gateway port
        """
        import urllib.request
        import json
        
        url = f"http://{host}:{port}/health"
        
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                print(f"Gateway Status: {data.get('status', 'unknown')}")
                print(f"  Uptime: {data.get('uptime', 0):.1f}s")
                print(f"  Agents: {data.get('agents', 0)}")
                print(f"  Sessions: {data.get('sessions', 0)}")
                print(f"  Clients: {data.get('clients', 0)}")
        except Exception as e:
            print(f"Gateway not reachable at {url}")
            print(f"Error: {e}")


def handle_gateway_command(args) -> int:
    """Handle gateway CLI command. [DEPRECATED]
    
    Args:
        args: List of CLI arguments (from main.py unknown_args) or argparse Namespace.
    """
    import argparse
    
    if isinstance(args, list):
        parser = argparse.ArgumentParser(
            prog="praisonai gateway",
            description="Manage the PraisonAI Gateway server",
        )
        subparsers = parser.add_subparsers(dest="gateway_command", help="Gateway commands")
        
        # start subcommand
        start_parser = subparsers.add_parser("start", help="Start the gateway server")
        start_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
        start_parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
        start_parser.add_argument("--agents", help="Path to agent configuration file")
        start_parser.add_argument("--config", dest="config_file", help="Path to gateway.yaml for multi-bot mode")
        
        # status subcommand
        status_parser = subparsers.add_parser("status", help="Check gateway status")
        status_parser.add_argument("--host", default="127.0.0.1", help="Gateway host (default: 127.0.0.1)")
        status_parser.add_argument("--port", type=int, default=8765, help="Gateway port (default: 8765)")
        
        try:
            args = parser.parse_args(args)
        except SystemExit:
            return 1
    
    handler = GatewayHandler()
    
    subcommand = getattr(args, "gateway_command", None) or "start"
    
    if subcommand == "start":
        handler.start(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
            agent_file=getattr(args, "agents", None),
            config_file=getattr(args, "config_file", None),
        )
    elif subcommand == "status":
        handler.status(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
        )
    else:
        print(f"Unknown gateway command: {subcommand}")
        print("Available commands: start, status")
        return 1
    return 0


def add_gateway_parser(subparsers) -> None:
    """Add gateway subparser to CLI."""
    gateway_parser = subparsers.add_parser(
        "gateway",
        help="Manage the WebSocket gateway",
    )
    
    gateway_subparsers = gateway_parser.add_subparsers(
        dest="gateway_command",
        help="Gateway commands",
    )
    
    start_parser = gateway_subparsers.add_parser(
        "start",
        help="Start the gateway server",
    )
    start_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765)",
    )
    start_parser.add_argument(
        "--agents",
        help="Path to agent configuration file",
    )
    start_parser.add_argument(
        "--config",
        dest="config_file",
        help="Path to gateway.yaml for multi-bot mode",
    )
    
    status_parser = gateway_subparsers.add_parser(
        "status",
        help="Check gateway status",
    )
    status_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Gateway host (default: 127.0.0.1)",
    )
    status_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Gateway port (default: 8765)",
    )
    
    gateway_parser.set_defaults(func=handle_gateway_command)
