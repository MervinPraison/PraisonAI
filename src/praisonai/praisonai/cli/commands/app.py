"""
CLI command for AgentApp - production deployment of AI agents.

Usage:
    praisonai app                    # Start server with default config
    praisonai app --port 9000        # Start on custom port
    praisonai app --config app.yaml  # Load from config file
    praisonai app --reload           # Enable auto-reload for development
"""

import click
from typing import Optional


@click.command("app")
@click.option("--port", "-p", type=int, default=8000, help="Port to listen on")
@click.option("--host", "-h", type=str, default="0.0.0.0", help="Host to bind to")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file (YAML)")
@click.option("--reload", "-r", is_flag=True, help="Enable auto-reload for development")
@click.option("--debug", "-d", is_flag=True, help="Enable debug mode")
@click.option("--name", "-n", type=str, default="PraisonAI App", help="Application name")
def app_command(
    port: int,
    host: str,
    config: Optional[str],
    reload: bool,
    debug: bool,
    name: str,
):
    """
    Start an AgentApp server for production deployment.
    
    AgentApp provides a FastAPI-based web service for deploying AI agents
    with REST and WebSocket endpoints.
    
    Examples:
    
        # Start with defaults (port 8000)
        praisonai app
        
        # Start on custom port
        praisonai app --port 9000
        
        # Enable auto-reload for development
        praisonai app --reload
        
        # Load agents from config file
        praisonai app --config agents.yaml
    """
    from rich.console import Console
    console = Console()
    
    try:
        from praisonai import AgentApp
        from praisonaiagents import AgentAppConfig
    except ImportError as e:
        console.print(f"[red]Error importing AgentApp: {e}[/red]")
        console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
        raise click.Abort()
    
    # Load agents from config file if provided
    agents = []
    if config:
        agents = _load_agents_from_config(config, console)
    
    # Create config
    app_config = AgentAppConfig(
        name=name,
        host=host,
        port=port,
        reload=reload,
        debug=debug,
    )
    
    # Create and start app
    console.print(f"\n[bold green]🚀 Starting {name}[/bold green]")
    console.print(f"[dim]Host: {host}:{port}[/dim]")
    if agents:
        console.print(f"[dim]Agents: {len(agents)}[/dim]")
    if reload:
        console.print("[yellow]Auto-reload enabled (development mode)[/yellow]")
    console.print()
    
    try:
        agent_app = AgentApp(
            name=name,
            agents=agents,
            config=app_config,
        )
        agent_app.serve()
    except ImportError as e:
        console.print(f"[red]Missing dependency: {e}[/red]")
        console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error starting server: {e}[/red]")
        raise click.Abort()


def _load_agents_from_config(config_path: str, console) -> list:
    """Load agents from a YAML config file."""
    import yaml
    from pathlib import Path
    
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        return []
    
    if not config_data:
        return []
    
    agents = []
    
    # Try to load agents from config
    agents_config = config_data.get('agents', [])
    if not agents_config and 'agent' in config_data:
        agents_config = [config_data['agent']]
    
    if agents_config:
        try:
            from praisonaiagents import Agent
            
            for agent_data in agents_config:
                if isinstance(agent_data, dict):
                    agent = Agent(
                        name=agent_data.get('name', 'Agent'),
                        role=agent_data.get('role'),
                        instructions=agent_data.get('instructions', agent_data.get('goal', '')),
                        llm=agent_data.get('llm'),
                    )
                    agents.append(agent)
                    console.print(f"[green]✓ Loaded agent: {agent.name}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load agents from config: {e}[/yellow]")
    
    return agents
