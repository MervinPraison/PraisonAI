"""
Gateway CLI commands for PraisonAI.

Provides CLI commands for managing the WebSocket gateway.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GatewayHandler:
    """Handler for gateway CLI commands."""
    
    def __init__(self):
        self._gateway = None
    
    def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        agent_file: Optional[str] = None,
    ) -> None:
        """Start the gateway server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            agent_file: Optional path to agent configuration file
        """
        try:
            from praisonai.gateway import WebSocketGateway
            from praisonaiagents.gateway import GatewayConfig
        except ImportError as e:
            print(f"Error: Gateway requires additional dependencies. {e}")
            print("Install with: pip install praisonai[api]")
            return
        
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


def handle_gateway_command(args) -> None:
    """Handle gateway CLI command.
    
    DEPRECATED: Use `praisonai serve gateway` instead.
    """
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai gateway' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve gateway' instead.\033[0m\n", file=sys.stderr)
    
    handler = GatewayHandler()
    
    subcommand = getattr(args, "gateway_command", None) or "start"
    
    if subcommand == "start":
        handler.start(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
            agent_file=getattr(args, "agents", None),
        )
    elif subcommand == "status":
        handler.status(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8765),
        )
    else:
        print(f"Unknown gateway command: {subcommand}")
        print("Available commands: start, status")


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
