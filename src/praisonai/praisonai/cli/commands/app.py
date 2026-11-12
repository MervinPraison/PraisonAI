"""
CLI command for AgentOS - production deployment of AI agents.

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
@click.option("--host", "-h", type=str, default="127.0.0.1",
              help="Host to bind to (pass 0.0.0.0 to expose; requires an API key)")
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
    Start an AgentOS server for production deployment.
    
    AgentOS provides a FastAPI-based web service for deploying AI agents
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
        from praisonai import AgentOS
        from praisonaiagents import AgentOSConfig
    except ImportError as e:
        console.print(f"[red]Error importing AgentOS: {e}[/red]")
        console.print("[yellow]Install with: pip install praisonai[api][/yellow]")
        raise click.Abort()
    
    # Load agents and server settings from config file if provided
    agents, server_cfg = [], {}
    if config:
        agents, server_cfg = _load_app_config(config, console)
    
    # Explicit CLI flags override YAML; YAML overrides CLI defaults.
    ctx = click.get_current_context()
    cli_values = dict(name=name, host=host, port=port, reload=reload, debug=debug)
    for key, value in cli_values.items():
        if key not in server_cfg or ctx.get_parameter_source(key) != click.core.ParameterSource.DEFAULT:
            server_cfg[key] = value
    app_config = AgentOSConfig(**server_cfg)
    name, host, port, reload = app_config.name, app_config.host, app_config.port, app_config.reload
    
    # Create and start app
    console.print(f"\n[bold green]🚀 Starting {name}[/bold green]")
    console.print(f"[dim]Host: {host}:{port}[/dim]")
    if agents:
        console.print(f"[dim]Agents: {len(agents)}[/dim]")
    if reload:
        console.print(
            "[yellow]--reload requested; note auto-reload is not supported for a "
            "programmatically-built AgentOS (the reload worker runs in a separate "
            "process). Serving without reload.[/yellow]"
        )
    console.print()
    
    try:
        agent_app = AgentOS(
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


def _load_app_config(config_path: str, console) -> tuple:
    """Load agents and AgentOSConfig fields from a YAML config file.

    Top-level keys matching ``AgentOSConfig`` fields (``api_key``,
    ``cors_origins``, ...) configure the server; each agent entry is passed
    to ``Agent`` with every key it accepts. Unknown keys are reported rather
    than silently dropped.
    """
    import dataclasses
    import inspect
    import yaml
    
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        return [], {}
    
    if not isinstance(config_data, dict):
        return [], {}
    
    from praisonaiagents import AgentOSConfig
    server_keys = {f.name for f in dataclasses.fields(AgentOSConfig)}
    server_cfg = {k: v for k, v in config_data.items() if k in server_keys}
    unknown = set(config_data) - server_keys - {'agent', 'agents'}
    if unknown:
        console.print(f"[yellow]Ignoring unknown top-level keys: {sorted(unknown)}[/yellow]")
    
    agents = []
    agents_config = config_data.get('agents') or []
    if not agents_config and 'agent' in config_data:
        agents_config = [config_data['agent']]
    
    if agents_config:
        try:
            from praisonaiagents import Agent
            agent_keys = {
                n for n, prm in inspect.signature(Agent.__init__).parameters.items()
                if n != 'self' and prm.kind not in (prm.VAR_POSITIONAL, prm.VAR_KEYWORD)
            }
            # Deprecated options Agent still accepts via **legacy_kwargs.
            agent_keys |= set(getattr(Agent, '_LEGACY_AGENT_PARAMS', {}))
            
            for agent_data in agents_config:
                if not isinstance(agent_data, dict):
                    continue
                kwargs = {k: v for k, v in agent_data.items() if k in agent_keys}
                kwargs.setdefault('name', 'Agent')
                if 'instructions' not in kwargs and 'goal' in agent_data:
                    kwargs['instructions'] = agent_data['goal']
                unknown = set(agent_data) - agent_keys
                if unknown:
                    console.print(f"[yellow]Ignoring unknown agent keys: {sorted(unknown)}[/yellow]")
                agent = Agent(**kwargs)
                agents.append(agent)
                console.print(f"[green]✓ Loaded agent: {agent.name}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load agents from config: {e}[/yellow]")
    
    return agents, server_cfg


# Expose the command under the name the praisonai-code lazy loader looks up
# via getattr(module, "app"), so the wrapper owns the `app` command when
# installed (C8.2). Without this alias the loader raises AttributeError and
# silently falls back to the inline duplicate in praisonai-code.
app = app_command
