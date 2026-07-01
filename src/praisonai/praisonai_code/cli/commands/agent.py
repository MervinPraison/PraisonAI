"""
Agent management commands for PraisonAI CLI.

Provides commands to list and inspect custom agent definitions.
"""

from typing import Optional

import typer

from praisonai.cli.output.console import get_output_controller

app = typer.Typer(help="Manage custom agents")


@app.command()
def list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """List all discovered custom agents."""
    output = get_output_controller()
    
    try:
        from praisonai.cli.features.custom_definitions import CustomDefinitionsDiscovery
        
        discovery = CustomDefinitionsDiscovery()
        discovery.discover()
        
        agents = discovery.list_agents()
        
        if not agents:
            output.print_info("No custom agents found.")
            output.print_info("Run 'praisonai init' to scaffold a starter .praisonai/ project,")
            output.print_info("or create agents in .praisonai/agents/*.md or ~/.praisonai/agents/*.md")
            return
        
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        table = Table(title="Custom Agents", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="yellow")
        table.add_column("Model", style="green")
        
        if verbose:
            table.add_column("Path", style="dim")
            table.add_column("Role", style="magenta")
        
        for agent in agents:
            row = [
                agent.name,
                agent.source,
                agent.model or "default",
            ]
            
            if verbose:
                row.extend([
                    str(agent.path),
                    agent.role or "Assistant"
                ])
            
            table.add_row(*row)
        
        console.print(table)
        
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def show(
    name: str = typer.Argument(help="Agent name to inspect"),
):
    """Show details of a specific agent."""
    output = get_output_controller()
    
    try:
        from praisonai.cli.features.custom_definitions import CustomDefinitionsDiscovery
        
        discovery = CustomDefinitionsDiscovery()
        agent = discovery.get_agent(name)
        
        if not agent:
            output.print_error(f"Agent '{name}' not found")
            raise typer.Exit(1)
        
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
        
        console = Console()
        
        # Build agent info
        info = f"""[bold cyan]Agent: {agent.name}[/bold cyan]
[yellow]Source:[/yellow] {agent.source}
[yellow]Path:[/yellow] {agent.path}
[yellow]Model:[/yellow] {agent.model or 'default'}
[yellow]Role:[/yellow] {agent.role or 'Assistant'}
[yellow]Goal:[/yellow] {agent.goal or 'N/A'}"""
        
        console.print(Panel(info, title="Agent Details", border_style="cyan"))
        
        if agent.instructions or agent.system_prompt:
            prompt_text = agent.instructions or agent.system_prompt
            syntax = Syntax(prompt_text, "markdown", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, title="System Prompt", border_style="green"))
        
        if agent.tools:
            tools_text = "\n".join(f"- {tool}" for tool in agent.tools)
            console.print(Panel(tools_text, title="Tools", border_style="yellow"))
    
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)