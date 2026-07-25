"""
Agent management commands for PraisonAI CLI.

Provides commands to list and inspect custom agent definitions.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Manage custom agents")


@app.command()
def list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """List all discovered custom agents."""
    output = get_output_controller()
    
    try:
        from praisonai_code.cli.features.custom_definitions import CustomDefinitionsDiscovery
        
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
def create(
    name: Optional[str] = typer.Argument(None, help="Agent name (file stem for .praisonai/agents/<name>.md)"),
    describe: Optional[str] = typer.Option(None, "--describe", "-d", help="One-line description of what the agent should do"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use (defaults to your detected provider)"),
    permission: Optional[str] = typer.Option(None, "--permission", "-p", help="Permission preset: read-only, review, full"),
    global_: bool = typer.Option(False, "--global", help="Write to user-global ~/.praisonai/agents/ instead of the project"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing agent definition"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: accept defaults, skip prompts"),
):
    """Author a new custom agent definition (interactive or scriptable).

    Interactive form prompts for the missing pieces; the non-interactive form
    (``--describe ... --permission ... --yes``) is scriptable for CI. Drafts a
    system prompt via the LLM when available and always writes a valid
    ``.praisonai/agents/<name>.md`` that ``praisonai run --agent <name>`` uses.
    """
    output = get_output_controller()

    try:
        from praisonai_code.cli.features.agent_scaffold import (
            DEFAULT_PERMISSION,
            PERMISSION_PRESETS,
            draft_system_prompt,
            resolve_agents_dir,
            validate_agent_name,
            write_agent_definition,
        )
        from praisonai_code.cli.features.custom_definitions import CustomDefinitionsDiscovery

        interactive = not yes

        try:
            from rich.prompt import Prompt
        except Exception:
            Prompt = None

        # Name.
        if not name:
            if interactive and Prompt is not None:
                name = Prompt.ask("Agent name").strip()
            if not name:
                output.print_error("An agent name is required (pass it as an argument or run interactively).")
                raise typer.Exit(1)

        # Validate early so path-unsafe names fail fast (before any LLM drafting).
        try:
            name = validate_agent_name(name)
        except ValueError as exc:
            output.print_error(str(exc))
            raise typer.Exit(1)

        # Description.
        description = describe
        if not description:
            if interactive and Prompt is not None:
                description = Prompt.ask("Describe what this agent does").strip()
            if not description:
                description = f"A helpful {name} agent."

        # Permission preset.
        if not permission:
            if interactive and Prompt is not None:
                permission = Prompt.ask(
                    "Permission preset",
                    choices=list(PERMISSION_PRESETS.keys()),
                    default=DEFAULT_PERMISSION,
                )
            else:
                permission = DEFAULT_PERMISSION
        if permission not in PERMISSION_PRESETS:
            output.print_error(
                f"Unknown permission preset '{permission}'. "
                f"Valid presets: {', '.join(PERMISSION_PRESETS)}"
            )
            raise typer.Exit(1)

        # Model (default via the shared resolver, mirroring init/run/setup).
        if not model:
            try:
                from ..configuration.model_resolver import resolve_default_model
                model = resolve_default_model(None, persist=False, notify=False)
            except Exception:
                model = None
            if interactive and Prompt is not None:
                model = Prompt.ask("Model", default=model or "").strip() or None

        role = name.replace("-", " ").replace("_", " ").title()
        goal = description

        # Draft the system prompt; degrade to an editable stub on any failure.
        body = draft_system_prompt(description, role, model)
        if body is None:
            output.print_warning("Could not draft a system prompt via the LLM; wrote an editable stub instead.")

        agents_dir = resolve_agents_dir(global_)
        try:
            path = write_agent_definition(
                name=name,
                description=description,
                role=role,
                goal=goal,
                model=model,
                permission=permission,
                agents_dir=agents_dir,
                body=body,
                force=force,
            )
        except FileExistsError as exc:
            output.print_error(
                f"Agent already exists: {exc}. Use --force to overwrite."
            )
            raise typer.Exit(1)

        # Post-write validation: re-parse the exact file we just wrote (not a
        # precedence lookup) so a global write is never validated against a
        # same-named project definition that ``run`` would actually resolve.
        discovery = CustomDefinitionsDiscovery()
        source = "user" if global_ else "project"
        reloaded = discovery._load_agent(path, source=source)
        if reloaded is None:
            output.print_warning(
                f"Wrote {path}, but it could not be re-parsed — check the frontmatter."
            )
        else:
            output.print_success(f"Created {path}")

        # If a higher-precedence definition shadows this name, ``run`` would pick
        # that one instead — warn so the reported next step is never misleading.
        effective = discovery.get_agent(name)
        if effective is not None and effective.path != path:
            output.print_warning(
                f"Another '{name}' agent takes precedence for 'run': {effective.path}. "
                "Rename this agent or remove the other to use it directly."
            )

        output.print_info("You can now run:")
        output.print_info(f'  praisonai run --agent {name} "..."')

    except typer.Exit:
        raise
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
        from praisonai_code.cli.features.custom_definitions import CustomDefinitionsDiscovery
        
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