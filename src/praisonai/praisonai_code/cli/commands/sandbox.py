"""
Sandbox command group for PraisonAI CLI.

Provides sandbox management commands inspired by moltbot's sandbox CLI.
Supports listing, explaining, and recreating sandbox containers.
"""

from typing import Optional

import typer

app = typer.Typer(
    help="Sandbox container management",
    no_args_is_help=True,
)


@app.command("status")
def sandbox_status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show sandbox status and configuration.
    
    Examples:
        praisonai sandbox status
        praisonai sandbox status --json
    """
    try:
        from rich.console import Console
        
        console = Console()
        
        # Check sandbox availability
        sandbox_info = _get_sandbox_info()
        
        if json_output:
            import json
            print(json.dumps(sandbox_info, indent=2))
        else:
            console.print("[bold cyan]Sandbox Status[/bold cyan]\n")
            
            status = "[green]Available[/green]" if sandbox_info["available"] else "[red]Not Available[/red]"
            console.print(f"Status: {status}")
            console.print(f"Mode: {sandbox_info.get('mode', 'off')}")
            console.print(f"Scope: {sandbox_info.get('scope', 'session')}")
            
            if sandbox_info.get("docker_available"):
                console.print("Docker: [green]Available[/green]")
                console.print(f"Image: {sandbox_info.get('image', 'default')}")
            else:
                console.print("Docker: [yellow]Not Available[/yellow]")
            
            if sandbox_info.get("containers"):
                console.print(f"\n[bold]Active Containers:[/bold] {len(sandbox_info['containers'])}")
                for container in sandbox_info["containers"]:
                    console.print(f"  - {container['name']} ({container['status']})")
                    
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("explain")
def sandbox_explain(
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Session key"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Explain effective sandbox policy and tool access.
    
    Shows the effective sandbox mode, scope, workspace access,
    and tool policy for a session or agent.
    
    Examples:
        praisonai sandbox explain
        praisonai sandbox explain --session main
        praisonai sandbox explain --agent work
    """
    try:
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        
        policy = _get_sandbox_policy(session, agent)
        
        if json_output:
            import json
            print(json.dumps(policy, indent=2))
        else:
            console.print("[bold cyan]Sandbox Policy[/bold cyan]\n")
            
            if session:
                console.print(f"Session: {session}")
            if agent:
                console.print(f"Agent: {agent}")
            
            console.print("\n[bold]Effective Settings:[/bold]")
            console.print(f"  Mode: {policy.get('mode', 'off')}")
            console.print(f"  Scope: {policy.get('scope', 'session')}")
            console.print(f"  Workspace Access: {policy.get('workspace_access', 'full')}")
            
            console.print("\n[bold]Tool Policy:[/bold]")
            table = Table()
            table.add_column("Tool", style="cyan")
            table.add_column("Access")
            table.add_column("Notes")
            
            for tool, access in policy.get("tools", {}).items():
                status = "[green]allowed[/green]" if access.get("allowed") else "[red]denied[/red]"
                table.add_row(tool, status, access.get("notes", "-"))
            
            console.print(table)
            
            if policy.get("elevated_gates"):
                console.print("\n[bold]Elevated Gates:[/bold]")
                for gate in policy["elevated_gates"]:
                    console.print(f"  - {gate}")
                    
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("list")
def sandbox_list(
    browser: bool = typer.Option(False, "--browser", help="List only browser containers"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List sandbox containers.
    
    Examples:
        praisonai sandbox list
        praisonai sandbox list --browser
        praisonai sandbox list --json
    """
    try:
        containers = _get_sandbox_containers(browser_only=browser)
        
        if json_output:
            import json
            print(json.dumps(containers, indent=2))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            title = "Browser Containers" if browser else "Sandbox Containers"
            table = Table(title=f"{title} ({len(containers)} found)")
            table.add_column("Name", style="cyan")
            table.add_column("Status")
            table.add_column("Image")
            table.add_column("Age")
            table.add_column("Session/Agent")
            
            for container in containers:
                status = "[green]running[/green]" if container.get("running") else "[dim]stopped[/dim]"
                table.add_row(
                    container.get("name", "-"),
                    status,
                    container.get("image", "-"),
                    container.get("age", "-"),
                    container.get("session", "-"),
                )
            
            console.print(table)
            
            if not containers:
                console.print("[dim]No containers found[/dim]")
                
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("recreate")
def sandbox_recreate(
    all_containers: bool = typer.Option(False, "--all", help="Recreate all containers"),
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Recreate for specific session"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Recreate for specific agent"),
    browser: bool = typer.Option(False, "--browser", help="Only recreate browser containers"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Recreate sandbox containers.
    
    Removes sandbox containers to force recreation with updated
    images or configuration. Containers are automatically recreated
    when the agent is next used.
    
    Examples:
        praisonai sandbox recreate --all
        praisonai sandbox recreate --session main
        praisonai sandbox recreate --agent mybot
        praisonai sandbox recreate --browser --force
    """
    if not any([all_containers, session, agent]):
        typer.echo("Error: Specify --all, --session, or --agent", err=True)
        raise typer.Exit(1)
    
    try:
        containers = _get_sandbox_containers(browser_only=browser)
        
        # Filter containers
        if session:
            containers = [c for c in containers if c.get("session") == session]
        if agent:
            containers = [c for c in containers if c.get("agent") == agent]
        
        if not containers:
            typer.echo("No matching containers found")
            return
        
        # Confirm
        if not force:
            typer.echo(f"Will recreate {len(containers)} container(s):")
            for c in containers:
                typer.echo(f"  - {c.get('name')}")
            
            if not typer.confirm("Continue?"):
                typer.echo("Cancelled")
                return
        
        # Remove containers
        removed = 0
        for container in containers:
            try:
                _remove_container(container.get("name"))
                removed += 1
                typer.echo(f"[green]✓[/green] Removed: {container.get('name')}")
            except Exception as e:
                typer.echo(f"[red]✗[/red] Failed to remove {container.get('name')}: {e}")
        
        typer.echo(f"\nRemoved {removed}/{len(containers)} containers")
        typer.echo("Containers will be recreated on next use")
        
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def _get_sandbox_info():
    """Get sandbox status information."""
    import shutil
    
    info = {
        "available": False,
        "mode": "off",
        "scope": "session",
        "docker_available": shutil.which("docker") is not None,
        "image": "praisonai-sandbox:latest",
        "containers": [],
    }
    
    # Check if Docker is available
    if info["docker_available"]:
        info["available"] = True
        
        # Try to list containers
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=praisonai-sbx-", "--format", "{{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        info["containers"].append({
                            "name": parts[0],
                            "status": parts[1],
                        })
        except Exception:
            pass
    
    return info


def _get_sandbox_policy(session: Optional[str], agent: Optional[str]):
    """Get effective sandbox policy."""
    return {
        "mode": "off",
        "scope": "session",
        "workspace_access": "full",
        "tools": {
            "exec": {"allowed": True, "notes": "Host execution"},
            "browser": {"allowed": True, "notes": "Browser automation"},
            "file_read": {"allowed": True, "notes": "Read workspace files"},
            "file_write": {"allowed": True, "notes": "Write workspace files"},
        },
        "elevated_gates": [],
    }


def _get_sandbox_containers(browser_only: bool = False):
    """Get list of sandbox containers."""
    containers = []
    
    try:
        import subprocess
        
        filter_name = "praisonai-browser-" if browser_only else "praisonai-sbx-"
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={filter_name}", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.CreatedAt}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 4:
                    containers.append({
                        "name": parts[0],
                        "running": "Up" in parts[1],
                        "status": parts[1],
                        "image": parts[2],
                        "age": parts[3],
                        "session": parts[0].split("-")[-1] if "-" in parts[0] else "-",
                    })
    except Exception:
        pass
    
    return containers


def _remove_container(name: str):
    """Remove a Docker container."""
    import subprocess
    
    # Stop if running
    subprocess.run(["docker", "stop", name], capture_output=True, timeout=10)
    # Remove
    result = subprocess.run(["docker", "rm", name], capture_output=True, timeout=10)
    
    if result.returncode != 0:
        raise Exception(result.stderr.decode() if result.stderr else "Unknown error")


@app.callback(invoke_without_command=True)
def sandbox_callback(ctx: typer.Context):
    """Show sandbox help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Sandbox - Container Management[/bold cyan]

Manage sandbox containers with: praisonai sandbox <command>

[bold]Commands:[/bold]
  [green]status[/green]      Show sandbox status
  [green]explain[/green]     Explain effective sandbox policy
  [green]list[/green]        List sandbox containers
  [green]recreate[/green]    Recreate containers

[bold]Examples:[/bold]
  praisonai sandbox status
  praisonai sandbox explain --agent work
  praisonai sandbox list --browser
  praisonai sandbox recreate --all --force
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
