"""PraisonAI Flow — Visual workflow builder powered by Langflow.

Provides `praisonai flow` CLI command to launch Langflow with
PraisonAI custom components (Agent, Agents, Task) pre-loaded.
"""

import typer

import click

app = typer.Typer(name="flow", help="Visual workflow builder (Langflow)")


@app.callback(invoke_without_command=True)
def flow_start(
    ctx: typer.Context,
    port: int = typer.Option(7860, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Host to bind to"),
    env_file: str = typer.Option(None, "--env-file", help="Path to .env file"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser on start"),
    log_level: str = typer.Option(
        "error",
        "--log-level",
        "-l",
        help="Logging level (debug, info, warning, error, critical)",
    ),
    backend_only: bool = typer.Option(
        False, "--backend-only", help="Run backend API only (no frontend UI)"
    ),
    components_path: str = typer.Option(
        None,
        "--components-path",
        help="Additional custom components directory",
    ),
):
    """Start PraisonAI Flow — visual workflow builder.

    Launches Langflow with PraisonAI Agent, AgentTeam, and Task components
    pre-loaded in the sidebar. Build complex AI workflows visually.

    Install: pip install praisonai[flow]

    Examples:
        praisonai flow
        praisonai flow --port 8080
        praisonai flow --host 0.0.0.0 --backend-only
    """
    if ctx.invoked_subcommand is not None:
        return

    import os
    import subprocess
    import sys
    from pathlib import Path

    from rich.console import Console

    console = Console()

    # Check langflow is installed
    try:
        import langflow  # noqa: F401
    except ImportError:
        console.print(
            "[red]Langflow is not installed.[/red]\n"
            "[yellow]Install with: pip install praisonai[flow][/yellow]"
        )
        raise typer.Abort()

    # Resolve PraisonAI components directory (absolute path)
    praison_components = str(
        (Path(__file__).parent.parent.parent / "flow" / "components").resolve()
    )

    # Set LANGFLOW_COMPONENTS_PATH env var (comma-separated for pydantic list parsing)
    env = os.environ.copy()
    existing = env.get("LANGFLOW_COMPONENTS_PATH", "")
    if components_path:
        all_paths = f"{praison_components},{components_path}"
    else:
        all_paths = praison_components
    env["LANGFLOW_COMPONENTS_PATH"] = (
        f"{all_paths},{existing}" if existing else all_paths
    )

    # Suppress macOS CoreFoundation fork safety warnings (harmless noise from multiprocessing)
    if sys.platform == "darwin":
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

    # Suppress noisy Openlayer/loguru debug messages unless user wants them
    if log_level.lower() not in ("debug",):
        env.setdefault("LOGURU_LEVEL", log_level.upper())

    # Build langflow run command
    cmd = [
        sys.executable,
        "-m",
        "langflow",
        "run",
        "--port",
        str(port),
        "--host",
        host,
        "--log-level",
        log_level,
    ]
    if backend_only:
        cmd.append("--backend-only")
    if env_file:
        cmd.extend(["--env-file", env_file])
    if no_open:
        cmd.extend(["--open-browser", "false"])

    console.print()
    console.print("[bold green]🚀 Starting PraisonAI Flow[/bold green]")
    console.print(f"[dim]Langflow + PraisonAI components on {host}:{port}[/dim]")
    console.print(
        f"[dim]Components: {praison_components}[/dim]"
    )
    console.print()

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        console.print("\n[yellow]PraisonAI Flow stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting Langflow: {e}[/red]")
        raise typer.Abort()


@app.command("import")
def flow_import(
    yaml_path: str = typer.Argument(..., help="Path to YAML workflow file"),
    langflow_url: str = typer.Option(
        "http://localhost:7860", 
        "--url", 
        help="Langflow server URL"
    ),
    dry_run: bool = typer.Option(
        False, 
        "--dry-run", 
        help="Preview JSON without uploading"
    ),
    open_browser: bool = typer.Option(
        False, 
        "--open", 
        help="Open imported flow in browser"
    ),
    output: str = typer.Option(
        None, 
        "--output", 
        "-o", 
        help="Save JSON to file instead of uploading"
    ),
):
    """Import YAML workflow into Langflow.
    
    Converts PraisonAI YAML workflow to Langflow JSON format and uploads
    to a running Langflow instance for visual editing.
    
    Examples:
        praisonai flow import workflow.yaml
        praisonai flow import workflow.yaml --dry-run
        praisonai flow import workflow.yaml --output flow.json
        praisonai flow import workflow.yaml --url http://localhost:8080
    """
    from pathlib import Path
    from rich.console import Console
    from rich.json import JSON
    
    console = Console()
    
    # Validate input file
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        console.print(f"[red]Error: File not found: {yaml_path}[/red]")
        raise typer.Abort()
    
    try:
        from praisonai.flow.converter import yaml_to_langflow_json
        
        console.print(f"[cyan]Converting {yaml_path} to Langflow format...[/cyan]")
        
        # Convert YAML to Langflow JSON
        langflow_json = yaml_to_langflow_json(str(yaml_file))
        
        # Dry run: just show the JSON
        if dry_run:
            console.print("\n[bold green]✅ Conversion Preview[/bold green]")
            console.print(JSON.from_data(langflow_json, indent=2))
            return
        
        # Save to file mode
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            import json
            with open(output_path, 'w') as f:
                json.dump(langflow_json, f, indent=2)
            
            console.print(f"[green]✅ Flow saved to {output_path}[/green]")
            return
        
        # Upload to Langflow
        from praisonai.flow.client import create_client
        
        console.print(f"[cyan]Connecting to Langflow at {langflow_url}...[/cyan]")
        client = create_client(langflow_url)
        
        # Check server health
        health = client.health_check()
        if health["status"] != "healthy":
            console.print(f"[red]Error: Langflow server not accessible at {langflow_url}[/red]")
            console.print("[yellow]Make sure Langflow is running: praisonai flow[/yellow]")
            raise typer.Abort()
        
        # Upload flow
        console.print("[cyan]Uploading flow to Langflow...[/cyan]")
        response = client.upload_flow(langflow_json)
        
        flow_id = response.get("id", response.get("flow_id", ""))
        flow_name = langflow_json.get("name", "Imported Flow")
        
        console.print(f"[green]✅ Flow '{flow_name}' imported successfully![/green]")
        console.print(f"[dim]Flow ID: {flow_id}[/dim]")
        
        # Generate flow URL
        if flow_id:
            flow_url = f"{langflow_url}/flow/{flow_id}"
            console.print(f"[blue]View: {flow_url}[/blue]")
            
            # Open browser if requested
            if open_browser:
                import webbrowser
                webbrowser.open(flow_url)
                console.print("[dim]Opening in browser...[/dim]")
        
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Install with: pip install 'praisonai[flow]'[/yellow]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]Error importing flow: {e}[/red]")
        raise typer.Abort()


@app.command("export")
def flow_export(
    flow_id: str = typer.Argument(..., help="Flow ID to export"),
    output: str = typer.Option(
        None, 
        "--output", 
        "-o", 
        help="Output YAML file path (default: flow_id.yaml)"
    ),
    langflow_url: str = typer.Option(
        "http://localhost:7860", 
        "--url", 
        help="Langflow server URL"
    ),
    format: str = typer.Option(
        "yaml",
        "--format",
        help="Output format (yaml, json)",
        click_type=click.Choice(["yaml", "json"])
    ),
):
    """Export Langflow flow to YAML format.
    
    Downloads a flow from Langflow and converts it back to PraisonAI 
    YAML format for use with the CLI.
    
    Examples:
        praisonai flow export abc-123-def
        praisonai flow export abc-123-def --output my_workflow.yaml
        praisonai flow export abc-123-def --format json
    """
    from pathlib import Path
    from rich.console import Console
    
    console = Console()
    
    try:
        from praisonai.flow.client import create_client
        
        console.print(f"[cyan]Connecting to Langflow at {langflow_url}...[/cyan]")
        client = create_client(langflow_url)
        
        # Check server health
        health = client.health_check()
        if health["status"] != "healthy":
            console.print(f"[red]Error: Langflow server not accessible at {langflow_url}[/red]")
            raise typer.Abort()
        
        # Download flow
        console.print(f"[cyan]Downloading flow {flow_id}...[/cyan]")
        flow_data = client.get_flow(flow_id)
        
        # Determine output file
        if not output:
            flow_name = flow_data.get("name", flow_id)
            safe_name = "".join(c for c in flow_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            output = f"{safe_name}.{format}"
        
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "json":
            # Save as JSON
            import json
            with open(output_path, 'w') as f:
                json.dump(flow_data, f, indent=2)
        else:
            # Convert to YAML
            from praisonai.flow.converter import langflow_json_to_yaml
            
            console.print("[cyan]Converting to YAML format...[/cyan]")
            yaml_content = langflow_json_to_yaml(flow_data)
            
            with open(output_path, 'w') as f:
                f.write(yaml_content)
        
        console.print(f"[green]✅ Flow exported to {output_path}[/green]")
        
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Install with: pip install 'praisonai[flow]'[/yellow]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]Error exporting flow: {e}[/red]")
        raise typer.Abort()


@app.command("list")
def flow_list(
    langflow_url: str = typer.Option(
        "http://localhost:7860", 
        "--url", 
        help="Langflow server URL"
    ),
    search: str = typer.Option(
        None,
        "--search",
        "-s", 
        help="Search flows by name or description"
    ),
):
    """List flows in Langflow server.
    
    Shows all flows with their IDs, names, and descriptions for
    easy identification and export.
    
    Examples:
        praisonai flow list
        praisonai flow list --search research
        praisonai flow list --url http://localhost:8080
    """
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    try:
        from praisonai.flow.client import create_client
        
        console.print(f"[cyan]Connecting to Langflow at {langflow_url}...[/cyan]")
        client = create_client(langflow_url)
        
        # Check server health
        health = client.health_check()
        if health["status"] != "healthy":
            console.print(f"[red]Error: Langflow server not accessible at {langflow_url}[/red]")
            raise typer.Abort()
        
        # Get flows
        if search:
            console.print(f"[cyan]Searching for flows matching '{search}'...[/cyan]")
            flows = client.search_flows(search)
        else:
            console.print("[cyan]Loading flows...[/cyan]")
            flows = client.list_flows()
        
        if not flows:
            if search:
                console.print(f"[yellow]No flows found matching '{search}'[/yellow]")
            else:
                console.print("[yellow]No flows found[/yellow]")
            return
        
        # Create table
        table = Table(title=f"Langflow Flows ({len(flows)} found)")
        table.add_column("ID", style="cyan", min_width=20)
        table.add_column("Name", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Created", style="blue")
        
        for flow in flows:
            flow_id = flow.get("id", "")[:20] + "..." if len(flow.get("id", "")) > 20 else flow.get("id", "")
            name = flow.get("name", "Unnamed")
            description = flow.get("description", "")[:50] + "..." if len(flow.get("description", "")) > 50 else flow.get("description", "")
            created = flow.get("created_at", "")[:10] if flow.get("created_at") else ""
            
            table.add_row(flow_id, name, description, created)
        
        console.print(table)
        
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("[yellow]Install with: pip install 'praisonai[flow]'[/yellow]")
        raise typer.Abort()
    except Exception as e:
        console.print(f"[red]Error listing flows: {e}[/red]")
        raise typer.Abort()


@app.command("version")
def flow_version():
    """Show Langflow version information."""
    from rich.console import Console

    console = Console()

    try:
        from langflow.utils.version import get_version_info

        info = get_version_info()
        console.print(f"[bold]Langflow[/bold]: {info.get('version', 'unknown')}")
        console.print(f"[bold]Package[/bold]: {info.get('package', 'unknown')}")
    except ImportError:
        console.print(
            "[red]Langflow is not installed.[/red]\n"
            "[yellow]Install with: pip install praisonai[flow][/yellow]"
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
